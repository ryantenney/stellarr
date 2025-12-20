import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		proxy: {
			'/api': 'http://localhost:8000',
			'/rss': 'http://localhost:8000',
			'/list': 'http://localhost:8000',
			'/webhook': 'http://localhost:8000',
			'/sync': 'http://localhost:8000'
		}
	}
});
