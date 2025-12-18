import { writable } from 'svelte/store';
import { browser } from '$app/environment';

// Auth store - persists to localStorage
const storedAuth = browser ? localStorage.getItem('authenticated') === 'true' : false;
export const authenticated = writable(storedAuth);

authenticated.subscribe((value) => {
	if (browser) {
		localStorage.setItem('authenticated', value.toString());
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
