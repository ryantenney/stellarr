import { browser } from '$app/environment';
import { init, register, locale } from 'svelte-i18n';

const defaultLocale = 'en';

register('en', () => import('./locales/en.json'));
register('es', () => import('./locales/es.json'));
register('fr', () => import('./locales/fr.json'));
register('de', () => import('./locales/de.json'));

export const supportedLocales = [
	{ code: 'en', name: 'English' },
	{ code: 'es', name: 'Español' },
	{ code: 'fr', name: 'Français' },
	{ code: 'de', name: 'Deutsch' }
];

export function initI18n() {
	init({
		fallbackLocale: defaultLocale,
		initialLocale: browser ? (localStorage.getItem('locale') || getPreferredLocale()) : defaultLocale
	});
}

function getPreferredLocale() {
	if (!browser) return defaultLocale;

	const browserLang = navigator.language.split('-')[0];
	const supported = supportedLocales.map(l => l.code);

	return supported.includes(browserLang) ? browserLang : defaultLocale;
}

export function setLocale(newLocale) {
	locale.set(newLocale);
	if (browser) {
		localStorage.setItem('locale', newLocale);
	}
}
