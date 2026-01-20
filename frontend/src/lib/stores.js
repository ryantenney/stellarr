import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';

// Session duration: 30 days in milliseconds
const SESSION_DURATION_MS = 30 * 24 * 60 * 60 * 1000;

// Library status cache duration: 24 hours (match backend trending cache)
const LIBRARY_STATUS_CACHE_MS = 24 * 60 * 60 * 1000;

// Check if session is still valid
function isSessionValid() {
	if (!browser) return false;

	const authData = localStorage.getItem('auth_session');
	if (!authData) return false;

	try {
		const session = JSON.parse(authData);
		if (!session.authenticated || !session.timestamp || !session.token) return false;

		const elapsed = Date.now() - session.timestamp;
		return elapsed < SESSION_DURATION_MS;
	} catch {
		return false;
	}
}

// Get the stored session token
export function getSessionToken() {
	if (!browser) return null;

	const authData = localStorage.getItem('auth_session');
	if (!authData) return null;

	try {
		const session = JSON.parse(authData);
		return session.token || null;
	} catch {
		return null;
	}
}

// Get the stored user name
export function getUserName() {
	if (!browser) return null;

	const authData = localStorage.getItem('auth_session');
	if (!authData) return null;

	try {
		const session = JSON.parse(authData);
		return session.name || null;
	} catch {
		return null;
	}
}

// Get session expiry info
export function getSessionInfo() {
	if (!browser) return null;

	const authData = localStorage.getItem('auth_session');
	if (!authData) return null;

	try {
		const session = JSON.parse(authData);
		if (!session.timestamp) return null;

		const expiresAt = new Date(session.timestamp + SESSION_DURATION_MS);
		const remainingMs = session.timestamp + SESSION_DURATION_MS - Date.now();
		const remainingDays = Math.ceil(remainingMs / (24 * 60 * 60 * 1000));

		return { expiresAt, remainingDays };
	} catch {
		return null;
	}
}

// Auth store - persists to localStorage with 30-day expiration
const storedAuth = isSessionValid();
export const authenticated = writable(storedAuth);

// Clear invalid session on load
if (browser && !storedAuth) {
	localStorage.removeItem('auth_session');
}

// Set authenticated state with token and name from backend
export function setAuthenticated(token, name = null) {
	if (browser && token) {
		const session = { authenticated: true, timestamp: Date.now(), token, name };
		localStorage.setItem('auth_session', JSON.stringify(session));
	}
	authenticated.set(true);
}

// Logout - clear session and library status
export function logout() {
	if (browser) {
		localStorage.removeItem('auth_session');
		localStorage.removeItem('library_status');
	}
	authenticated.set(false);
}

// Password store (not persisted for security)
export const password = writable('');

// Requests store
export const requests = writable([]);

// Loading state
export const loading = writable(false);

// Toast notifications
export const toasts = writable([]);

export function addToast(message, type = 'info', duration = 3000) {
	const id = Date.now();
	toasts.update((t) => [...t, { id, message, type }]);
	setTimeout(() => {
		toasts.update((t) => t.filter((toast) => toast.id !== id));
	}, duration);
}

// =============================================================================
// Library Status Store - Cached library and request state for fast hydration
// =============================================================================

// Shape: { library: {movie: [], tv: []}, requests: [], timestamp: number }
function loadLibraryStatus() {
	if (!browser) return null;

	const data = localStorage.getItem('library_status');
	if (!data) return null;

	try {
		const parsed = JSON.parse(data);
		// Check if cache is still valid
		if (parsed.timestamp && Date.now() - parsed.timestamp < LIBRARY_STATUS_CACHE_MS) {
			return parsed;
		}
		// Cache expired, but still return it for immediate hydration
		// (will be refreshed in background)
		return parsed;
	} catch {
		return null;
	}
}

const initialLibraryStatus = loadLibraryStatus() || {
	library: { movie: [], tv: [] },
	requests: [],
	timestamp: 0
};

export const libraryStatus = writable(initialLibraryStatus);

// Persist to localStorage on changes
if (browser) {
	libraryStatus.subscribe((value) => {
		if (value && value.timestamp) {
			localStorage.setItem('library_status', JSON.stringify(value));
		}
	});
}

// Update the library status from API response
export function updateLibraryStatus(data) {
	libraryStatus.set({
		library: data.library || { movie: [], tv: [] },
		requests: data.requests || [],
		timestamp: Date.now()
	});
}

// Derived store: Set of library TMDB IDs for fast lookup
export const librarySet = derived(libraryStatus, ($status) => {
	const set = new Set();
	if ($status.library) {
		for (const id of $status.library.movie || []) {
			set.add(`movie:${id}`);
		}
		for (const id of $status.library.tv || []) {
			set.add(`tv:${id}`);
		}
	}
	return set;
});

// Derived store: Map of request TMDB IDs for fast lookup
export const requestsMap = derived(libraryStatus, ($status) => {
	const map = new Map();
	if ($status.requests) {
		for (const req of $status.requests) {
			map.set(`${req.media_type}:${req.tmdb_id}`, req);
		}
	}
	return map;
});

// Add an item to requests optimistically
export function addToRequestsOptimistic(tmdbId, mediaType, title) {
	libraryStatus.update((status) => {
		const newRequest = {
			tmdb_id: tmdbId,
			media_type: mediaType,
			title: title,
			created_at: new Date().toISOString()
		};
		return {
			...status,
			requests: [...status.requests, newRequest],
			timestamp: Date.now()
		};
	});
}

// Remove an item from requests optimistically
export function removeFromRequestsOptimistic(tmdbId, mediaType) {
	libraryStatus.update((status) => {
		return {
			...status,
			requests: status.requests.filter(
				(r) => !(Number(r.tmdb_id) === Number(tmdbId) && r.media_type === mediaType)
			),
			timestamp: Date.now()
		};
	});
}

// Clear library status on logout
export function clearLibraryStatus() {
	if (browser) {
		localStorage.removeItem('library_status');
	}
	libraryStatus.set({
		library: { movie: [], tv: [] },
		requests: [],
		timestamp: 0
	});
}

// =============================================================================
// Push Notifications Store
// =============================================================================

// Track push subscription state
export const pushSubscribed = writable(false);
export const pushSupported = writable(false);
export const pushPermission = writable('default');
export const iosBrowserNeedsPwa = writable(false);

// Detect iOS device
function isIOS() {
	if (!browser) return false;
	return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
		(navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

// Detect if running as installed PWA
function isInstalledPwa() {
	if (!browser) return false;
	return window.matchMedia('(display-mode: standalone)').matches ||
		window.navigator.standalone === true;
}

// Check if push is supported
export function checkPushSupport() {
	if (!browser) return false;
	const supported = 'serviceWorker' in navigator && 'PushManager' in window;
	pushSupported.set(supported);

	// iOS browser (not installed as PWA) can support push if installed
	if (!supported && isIOS() && !isInstalledPwa()) {
		iosBrowserNeedsPwa.set(true);
	}

	return supported;
}

// Check current notification permission
export function checkPushPermission() {
	if (!browser || !('Notification' in window)) return 'denied';
	const permission = Notification.permission;
	pushPermission.set(permission);
	return permission;
}

// Initialize push state on load
if (browser) {
	checkPushSupport();
	checkPushPermission();
}
