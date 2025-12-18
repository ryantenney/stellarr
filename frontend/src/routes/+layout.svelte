<script>
	import { authenticated } from '$lib/stores.js';
	import { toasts } from '$lib/stores.js';
</script>

<svelte:head>
	<style>
		:root {
			--bg-primary: #0f0f0f;
			--bg-secondary: #1a1a1a;
			--bg-tertiary: #252525;
			--text-primary: #ffffff;
			--text-secondary: #a0a0a0;
			--accent: #7b2cbf;
			--accent-hover: #9d4edd;
			--success: #10b981;
			--error: #ef4444;
			--warning: #f59e0b;
			--border: #333;
		}

		* {
			box-sizing: border-box;
			margin: 0;
			padding: 0;
		}

		body {
			font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
			background-color: var(--bg-primary);
			color: var(--text-primary);
			min-height: 100vh;
		}
	</style>
</svelte:head>

<div class="app">
	<header>
		<div class="header-content">
			<a href="/" class="logo">
				<span class="logo-icon">🎬</span>
				<span class="logo-text">Overseer Lite</span>
			</a>
			{#if $authenticated}
				<nav>
					<a href="/">Search</a>
					<a href="/requests">My Requests</a>
					<button class="logout-btn" on:click={() => authenticated.set(false)}>Logout</button>
				</nav>
			{/if}
		</div>
	</header>

	<main>
		<slot />
	</main>

	<!-- Toast notifications -->
	<div class="toast-container">
		{#each $toasts as toast (toast.id)}
			<div class="toast toast-{toast.type}">
				{toast.message}
			</div>
		{/each}
	</div>
</div>

<style>
	.app {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
	}

	header {
		background: var(--bg-secondary);
		border-bottom: 1px solid var(--border);
		padding: 1rem 2rem;
		position: sticky;
		top: 0;
		z-index: 100;
	}

	.header-content {
		max-width: 1400px;
		margin: 0 auto;
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.logo {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		text-decoration: none;
		color: var(--text-primary);
	}

	.logo-icon {
		font-size: 1.5rem;
	}

	.logo-text {
		font-size: 1.25rem;
		font-weight: 600;
	}

	nav {
		display: flex;
		gap: 1.5rem;
		align-items: center;
	}

	nav a {
		color: var(--text-secondary);
		text-decoration: none;
		transition: color 0.2s;
	}

	nav a:hover {
		color: var(--text-primary);
	}

	.logout-btn {
		background: transparent;
		border: 1px solid var(--border);
		color: var(--text-secondary);
		padding: 0.5rem 1rem;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: all 0.2s;
	}

	.logout-btn:hover {
		border-color: var(--error);
		color: var(--error);
	}

	main {
		flex: 1;
		max-width: 1400px;
		margin: 0 auto;
		padding: 2rem;
		width: 100%;
	}

	.toast-container {
		position: fixed;
		bottom: 1rem;
		right: 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		z-index: 1000;
	}

	.toast {
		padding: 1rem 1.5rem;
		border-radius: 0.5rem;
		background: var(--bg-tertiary);
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
		animation: slideIn 0.3s ease;
	}

	.toast-success {
		border-left: 4px solid var(--success);
	}

	.toast-error {
		border-left: 4px solid var(--error);
	}

	.toast-info {
		border-left: 4px solid var(--accent);
	}

	@keyframes slideIn {
		from {
			transform: translateX(100%);
			opacity: 0;
		}
		to {
			transform: translateX(0);
			opacity: 1;
		}
	}

	@media (max-width: 768px) {
		header {
			padding: 1rem;
		}

		nav {
			gap: 1rem;
		}

		main {
			padding: 1rem;
		}
	}
</style>
