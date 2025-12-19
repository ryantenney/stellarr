import { getSessionToken, getUserName, logout } from './stores.js';

const API_BASE = '/api';

// Compute SHA256 hash for challenge-response auth
async function sha256(message) {
	const msgBuffer = new TextEncoder().encode(message);
	const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
	const hashArray = Array.from(new Uint8Array(hashBuffer));
	return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
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
	// Challenge-response auth: hash origin + timestamp + password
	const origin = window.location.origin;
	const timestamp = Math.floor(Date.now() / 1000);
	const challengeString = `${origin}:${timestamp}:${password}`;
	const hash = await sha256(challengeString);

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
