import { writable } from 'svelte/store';
import { browser } from '$app/environment';

// Session duration: 30 days in milliseconds
const SESSION_DURATION_MS = 30 * 24 * 60 * 60 * 1000;

// Check if session is still valid
function isSessionValid() {
	if (!browser) return false;

	const authData = localStorage.getItem('auth_session');
	if (!authData) return false;

	try {
		const session = JSON.parse(authData);
		if (!session.authenticated || !session.timestamp) return false;

		const elapsed = Date.now() - session.timestamp;
		return elapsed < SESSION_DURATION_MS;
	} catch {
		return false;
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

authenticated.subscribe((value) => {
	if (browser) {
		if (value) {
			// Store auth with timestamp for expiration tracking
			const session = { authenticated: true, timestamp: Date.now() };
			localStorage.setItem('auth_session', JSON.stringify(session));
		} else {
			localStorage.removeItem('auth_session');
		}
	}
});

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
