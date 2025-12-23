import { getSessionToken, getUserName, logout, getTrendingKey } from './stores.js';

const API_BASE = '/api';

// Cached auth params (fetched from backend)
let authParamsCache = null;

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

export async function verifyPassword(password, name) {
	// Fetch PBKDF2 iterations from backend (single source of truth)
	const { iterations } = await getAuthParams();

	// Challenge-response auth with PBKDF2 key derivation
	const origin = window.location.origin;
	const timestamp = Math.floor(Date.now() / 1000);

	// PBKDF2 makes brute-force attacks computationally expensive
	const derivedKey = await pbkdf2DeriveKey(password, origin, iterations);
	const hash = await sha256(`${derivedKey}:${timestamp}`);

	return request('/auth/verify', {
		method: 'POST',
		body: JSON.stringify({ origin, timestamp, hash, name })
	}, false);  // No auth required for login
}

export async function search(query, mediaType = null, page = 1) {
	return request('/search', {
		method: 'POST',
		body: JSON.stringify({ query, media_type: mediaType, page })
	});
}

export async function getTrending(mediaType = 'all') {
	// Trending endpoint is now public but requires the trending key
	const key = getTrendingKey();
	if (!key) {
		// Return empty results if no key available yet
		// (library-status will populate the key, then caller can retry)
		return { results: [] };
	}

	// Direct fetch without auth header (public endpoint)
	const response = await fetch(`${API_BASE}/trending?media_type=${mediaType}&key=${key}`);

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
