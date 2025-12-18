import { getSessionToken, logout } from './stores.js';

const API_BASE = '/api';

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

export async function verifyPassword(password) {
	return request('/auth/verify', {
		method: 'POST',
		body: JSON.stringify({ password })
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
	return request('/request', {
		method: 'POST',
		body: JSON.stringify({ tmdb_id: tmdbId, media_type: mediaType })
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
