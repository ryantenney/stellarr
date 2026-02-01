import { getSessionToken, getUserName, logout, getTenantSlug } from './stores.js';

const API_BASE = '/api';

// Cached auth params (fetched from backend)
let authParamsCache = null;

// Check if running in multi-tenant mode (cached)
export function isMultiTenant() {
	return authParamsCache?.multi_tenant || false;
}

// Compute SHA256 hash
async function sha256(message) {
	const msgBuffer = new TextEncoder().encode(message);
	const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
	const hashArray = Array.from(new Uint8Array(hashBuffer));
	return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

// Fetch auth params from backend (cached)
async function getAuthParams() {
	if (authParamsCache) {
		return authParamsCache;
	}
	const response = await fetch(`${API_BASE}/auth/params`);
	if (!response.ok) {
		throw new Error('Failed to fetch auth params');
	}
	authParamsCache = await response.json();
	return authParamsCache;
}

// Preload auth params to warm up Lambda on page load
export function preloadAuthParams() {
	getAuthParams().catch(() => {});
}

// Warm up Lambda by hitting a lightweight endpoint
export async function warmup() {
	try {
		await fetch(`${API_BASE}/auth/params`);
	} catch {
		// Ignore errors - this is just a warmup
	}
}

// Derive key using PBKDF2 (brute-force resistant)
async function pbkdf2DeriveKey(password, salt, iterations) {
	const encoder = new TextEncoder();

	// Import password as a CryptoKey
	const passwordKey = await crypto.subtle.importKey(
		'raw',
		encoder.encode(password),
		'PBKDF2',
		false,
		['deriveBits']
	);

	// Derive 256 bits using PBKDF2
	const derivedBits = await crypto.subtle.deriveBits(
		{
			name: 'PBKDF2',
			salt: encoder.encode(salt),
			iterations,
			hash: 'SHA-256'
		},
		passwordKey,
		256  // 256 bits = 32 bytes
	);

	// Convert to hex string
	const derivedArray = Array.from(new Uint8Array(derivedBits));
	return derivedArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

async function request(endpoint, options = {}, requiresAuth = true) {
	const headers = {
		'Content-Type': 'application/json',
		...options.headers
	};

	// Add auth token for protected endpoints
	if (requiresAuth) {
		const token = getSessionToken();
		if (token) {
			headers['Authorization'] = `Bearer ${token}`;
		}
	}

	const response = await fetch(`${API_BASE}${endpoint}`, {
		...options,
		headers
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: 'Request failed' }));

		// Handle expired/invalid token
		if (response.status === 401 && requiresAuth) {
			logout();
		}

		throw new Error(error.detail || 'Request failed');
	}

	return response.json();
}

export async function verifyPassword(password, name, tenantSlug = null) {
	// Fetch auth params to check if multi-tenant mode
	const params = await getAuthParams();

	// In multi-tenant mode with a tenant context, use guest login
	if (params.multi_tenant && tenantSlug) {
		return loginGuest(tenantSlug, password, name);
	}

	// Legacy single-tenant mode: use PBKDF2 challenge-response
	const { iterations } = params;

	// Challenge-response auth with PBKDF2 key derivation
	const origin = window.location.origin;
	const timestamp = Math.floor(Date.now() / 1000);

	// PBKDF2 makes brute-force attacks computationally expensive
	const derivedKey = await pbkdf2DeriveKey(password, origin, iterations);
	const hash = await sha256(`${derivedKey}:${timestamp}`);

	const result = await request('/auth/verify', {
		method: 'POST',
		body: JSON.stringify({ origin, timestamp, hash, name })
	}, false);

	// Return in consistent format with guest login
	return {
		token: result.token,
		name: name,
		userType: 'legacy',
		tenant: null
	};
}

// Guest login for multi-tenant mode
export async function loginGuest(tenantSlug, accessCode, displayName = null) {
	const response = await fetch('/auth/guest', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			tenant_slug: tenantSlug,
			access_code: accessCode,
			display_name: displayName
		})
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: 'Login failed' }));
		throw new Error(error.detail || 'Invalid access code');
	}

	const data = await response.json();

	return {
		token: data.token,
		name: displayName,
		userType: 'guest',
		tenant: data.tenant,
		guestId: data.guest_id
	};
}

// Fetch tenant info by slug (for resolving tenant from URL)
export async function getTenantInfo(slug) {
	const response = await fetch(`/auth/tenant/${slug}`);
	if (!response.ok) {
		return null;
	}
	return response.json();
}

// --- Plex OAuth (for owners) ---

export async function initPlexLogin() {
	const response = await fetch('/auth/plex/login');
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: 'Failed to start Plex login' }));
		throw new Error(error.detail);
	}
	return response.json();
}

export async function pollPlexLogin(pinId) {
	const response = await fetch(`/auth/plex/poll/${pinId}`);
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: 'Failed to check Plex login' }));
		throw new Error(error.detail);
	}
	return response.json();
}

export async function completePlexCallback(pinId) {
	const response = await fetch(`/auth/plex/callback?pin_id=${pinId}`);
	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: 'Failed to complete Plex login' }));
		throw new Error(error.detail);
	}
	return response.json();
}

// Get current user info
export async function getCurrentUser() {
	return request('/auth/me', {}, true);
}

export async function search(query, mediaType = null, page = 1) {
	return request('/search', {
		method: 'POST',
		body: JSON.stringify({ query, media_type: mediaType, page })
	});
}

export async function getTrending(mediaType = 'all') {
	// Trending data is served as static JSON files from S3 via CloudFront
	// No authentication required - this is public TMDB data
	// Files are locale-specific: trending-all-en.json, trending-movie-fr.json, etc.
	const locale = localStorage.getItem('locale') || navigator.language.split('-')[0] || 'en';
	// Fallback to 'en' if locale not in supported list
	const supportedLocales = ['en', 'es', 'fr', 'de'];
	const effectiveLocale = supportedLocales.includes(locale) ? locale : 'en';

	const response = await fetch(`/trending-${mediaType}-${effectiveLocale}.json`);

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: 'Request failed' }));
		throw new Error(error.detail || 'Request failed');
	}

	return response.json();
}

export async function getRequests(mediaType = null) {
	const url = mediaType ? `/requests?media_type=${mediaType}` : '/requests';
	return request(url);
}

export async function addRequest(tmdbId, mediaType) {
	const requestedBy = getUserName();
	return request('/request', {
		method: 'POST',
		body: JSON.stringify({
			tmdb_id: tmdbId,
			media_type: mediaType,
			requested_by: requestedBy
		})
	});
}

export async function removeRequest(tmdbId, mediaType) {
	return request(`/request/${mediaType}/${tmdbId}`, {
		method: 'DELETE'
	});
}

export async function getFeedInfo() {
	return request('/feeds');
}

export async function getLibraryStatus() {
	return request('/library-status');
}

// --- Push Notifications ---

export async function getVapidPublicKey() {
	return request('/push/vapid-public-key');
}

export async function subscribePush(subscription) {
	return request('/push/subscribe', {
		method: 'POST',
		body: JSON.stringify({
			endpoint: subscription.endpoint,
			keys: {
				p256dh: subscription.keys.p256dh,
				auth: subscription.keys.auth
			}
		})
	});
}

export async function unsubscribePush() {
	return request('/push/subscribe', {
		method: 'DELETE'
	});
}

export async function getPushStatus() {
	return request('/push/status');
}
