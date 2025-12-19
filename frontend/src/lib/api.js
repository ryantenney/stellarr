import { getSessionToken, getUserName, logout } from './stores.js';

const API_BASE = '/api';

// PBKDF2 iterations - must match backend
const PBKDF2_ITERATIONS = 100000;

// Compute SHA256 hash
async function sha256(message) {
	const msgBuffer = new TextEncoder().encode(message);
	const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
	const hashArray = Array.from(new Uint8Array(hashBuffer));
	return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

// Derive key using PBKDF2 (brute-force resistant)
async function pbkdf2DeriveKey(password, salt) {
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
			iterations: PBKDF2_ITERATIONS,
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
	// Challenge-response auth with PBKDF2 key derivation
	// 1. Derive key: PBKDF2(password, salt=origin, iterations=100000)
	// 2. Hash: SHA256(derived_key:timestamp)
	const origin = window.location.origin;
	const timestamp = Math.floor(Date.now() / 1000);

	// PBKDF2 makes brute-force attacks computationally expensive
	const derivedKey = await pbkdf2DeriveKey(password, origin);
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
	return request(`/trending?media_type=${mediaType}`);
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
