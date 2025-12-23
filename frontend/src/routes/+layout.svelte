<script>
	import { onMount } from 'svelte';
	import { authenticated, logout, toasts, addToast, updateLibraryStatus } from '$lib/stores.js';
	import { preloadAuthParams, getFeedInfo, getLibraryStatus } from '$lib/api.js';

	let showFeedModal = false;
	let feedInfo = null;
	let loadingFeeds = false;

	onMount(() => {
		// Preload auth params on page load to warm up Lambda
		preloadAuthParams();

		// If authenticated, fetch library status in background
		if ($authenticated) {
			refreshLibraryStatus();
		}
	});

	// Fetch library status and update store
	async function refreshLibraryStatus() {
		try {
			const data = await getLibraryStatus();
			updateLibraryStatus(data);
		} catch (error) {
			console.error('Failed to fetch library status:', error);
		}
	}

	async function openFeedModal() {
		showFeedModal = true;
		if (!feedInfo) {
			loadingFeeds = true;
			try {
				feedInfo = await getFeedInfo();
			} catch (error) {
				console.error('Failed to load feed info:', error);
			} finally {
				loadingFeeds = false;
			}
		}
	}

	function copyUrl(url) {
		navigator.clipboard.writeText(url);
		addToast('URL copied to clipboard', 'success');
	}
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

		html {
			overscroll-behavior: none;
		}

		body {
			font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
			background-color: var(--bg-primary);
			color: var(--text-primary);
			min-height: 100vh;
			overscroll-behavior: none;
			/* Disable text selection on UI elements */
			-webkit-user-select: none;
			user-select: none;
			/* Disable tap highlight on mobile */
			-webkit-tap-highlight-color: transparent;
			/* Smooth scrolling */
			-webkit-overflow-scrolling: touch;
			/* Prevent pull-to-refresh */
			overflow-y: auto;
		}

		/* Allow text selection in content areas */
		p, h1, h2, h3, h4, h5, h6, .selectable {
			-webkit-user-select: text;
			user-select: text;
		}

		/* Disable callout on long-press (iOS) */
		a, button, img {
			-webkit-touch-callout: none;
		}

		/* Prevent image dragging */
		img {
			-webkit-user-drag: none;
			user-drag: none;
		}

		/* Fix for iOS input zoom - ensure inputs are 16px+ */
		input, textarea, select {
			font-size: 16px;
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
					<a href="/requests">Requests</a>
					<button class="nav-btn desktop-only" on:click={openFeedModal}>Feeds</button>
					<button class="logout-btn" on:click={logout} title="Logout">
						<span class="logout-text">Logout</span>
						<span class="logout-icon">⏻</span>
					</button>
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

	<!-- Feed URLs Modal -->
	{#if showFeedModal}
		<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
		<div class="modal-overlay" on:click={() => showFeedModal = false}>
			<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
			<div class="modal" on:click|stopPropagation>
				<div class="modal-header">
					<h2>Feed URLs for Sonarr/Radarr</h2>
					<button class="close-btn" on:click={() => showFeedModal = false}>&times;</button>
				</div>
				<div class="modal-content">
					{#if loadingFeeds}
						<div class="loading">Loading feed info...</div>
					{:else if feedInfo}
						{#if feedInfo.token_required}
							<p class="token-notice">Feed token is required. URLs include the token parameter.</p>
						{/if}

						<div class="feed-section">
							<h3>Radarr (Movies)</h3>
							<div class="feed-item recommended">
								<div class="feed-info">
									<strong>{feedInfo.feeds.radarr.name}</strong>
									<span class="badge">Recommended</span>
									<p>{feedInfo.feeds.radarr.description}</p>
									<code>{feedInfo.feeds.radarr.setup}</code>
								</div>
								<button on:click={() => copyUrl(feedInfo.feeds.radarr.url)}>Copy URL</button>
							</div>
							<div class="feed-item">
								<div class="feed-info">
									<strong>{feedInfo.feeds.radarr_rss.name}</strong>
									<p>{feedInfo.feeds.radarr_rss.description}</p>
								</div>
								<button on:click={() => copyUrl(feedInfo.feeds.radarr_rss.url)}>Copy URL</button>
							</div>
						</div>

						<div class="feed-section">
							<h3>Sonarr (TV Shows)</h3>
							<div class="feed-item recommended">
								<div class="feed-info">
									<strong>{feedInfo.feeds.sonarr.name}</strong>
									<span class="badge">Recommended</span>
									<p>{feedInfo.feeds.sonarr.description}</p>
									<code>{feedInfo.feeds.sonarr.setup}</code>
								</div>
								<button on:click={() => copyUrl(feedInfo.feeds.sonarr.url)}>Copy URL</button>
							</div>
							<div class="feed-item">
								<div class="feed-info">
									<strong>{feedInfo.feeds.tv_rss.name}</strong>
									<p>{feedInfo.feeds.tv_rss.description}</p>
								</div>
								<button on:click={() => copyUrl(feedInfo.feeds.tv_rss.url)}>Copy URL</button>
							</div>
						</div>

						<div class="feed-section">
							<h3>Combined</h3>
							<div class="feed-item">
								<div class="feed-info">
									<strong>{feedInfo.feeds.all_rss.name}</strong>
									<p>{feedInfo.feeds.all_rss.description}</p>
								</div>
								<button on:click={() => copyUrl(feedInfo.feeds.all_rss.url)}>Copy URL</button>
							</div>
						</div>
					{:else}
						<div class="error">Failed to load feed info</div>
					{/if}
				</div>
			</div>
		</div>
	{/if}
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

	nav a:hover,
	nav a:active {
		color: var(--text-primary);
	}

	.nav-btn {
		background: transparent;
		border: none;
		color: var(--text-secondary);
		cursor: pointer;
		font-size: inherit;
		padding: 0;
		transition: color 0.2s;
	}

	.nav-btn:hover,
	.nav-btn:active {
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

	.logout-btn:hover,
	.logout-btn:active {
		border-color: var(--error);
		color: var(--error);
	}

	.logout-icon {
		display: none;
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

	.desktop-only {
		display: inline;
	}

	@media (max-width: 768px) {
		header {
			padding: 0.75rem 1rem;
		}

		nav {
			gap: 0.75rem;
		}

		.desktop-only {
			display: none;
		}

		.logout-btn {
			padding: 0.4rem 0.5rem;
			border: none;
			background: none;
		}

		.logout-text {
			display: none;
		}

		.logout-icon {
			display: inline;
			font-size: 1.1rem;
		}

		main {
			padding: 1rem;
		}
	}

	/* Modal styles */
	.modal-overlay {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.8);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: 1rem;
	}

	.modal {
		background: var(--bg-secondary);
		border-radius: 1rem;
		max-width: 600px;
		width: 100%;
		max-height: min(90vh, 100dvh);
		overflow-y: auto;
	}

	.modal-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1.5rem;
		border-bottom: 1px solid var(--border);
	}

	.modal-header h2 {
		margin: 0;
		font-size: 1.25rem;
	}

	.close-btn {
		background: none;
		border: none;
		font-size: 1.5rem;
		color: var(--text-secondary);
		cursor: pointer;
		min-width: 44px;
		min-height: 44px;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 50%;
		transition: color 0.2s, background 0.2s;
	}

	.close-btn:hover,
	.close-btn:active {
		color: var(--text-primary);
		background: var(--bg-tertiary);
	}

	.modal-content {
		padding: 1.5rem;
	}

	.loading, .error {
		text-align: center;
		color: var(--text-secondary);
		padding: 2rem;
	}

	.token-notice {
		background: var(--bg-tertiary);
		padding: 0.75rem 1rem;
		border-radius: 0.5rem;
		margin-bottom: 1.5rem;
		color: var(--warning);
		font-size: 0.9rem;
	}

	.feed-section {
		margin-bottom: 1.5rem;
	}

	.feed-section h3 {
		font-size: 1rem;
		margin-bottom: 0.75rem;
		color: var(--text-secondary);
	}

	.feed-item {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		padding: 1rem;
		background: var(--bg-tertiary);
		border-radius: 0.5rem;
		margin-bottom: 0.5rem;
		gap: 1rem;
	}

	.feed-item.recommended {
		border: 1px solid var(--accent);
	}

	.feed-info {
		flex: 1;
	}

	.feed-info strong {
		display: block;
		margin-bottom: 0.25rem;
	}

	.feed-info p {
		font-size: 0.85rem;
		color: var(--text-secondary);
		margin: 0.25rem 0;
	}

	.feed-info code {
		font-size: 0.75rem;
		color: var(--text-secondary);
		background: var(--bg-secondary);
		padding: 0.25rem 0.5rem;
		border-radius: 0.25rem;
	}

	.badge {
		display: inline-block;
		background: var(--accent);
		color: white;
		font-size: 0.7rem;
		padding: 0.2rem 0.5rem;
		border-radius: 0.25rem;
		margin-left: 0.5rem;
		vertical-align: middle;
	}

	.feed-item button {
		padding: 0.5rem 1rem;
		background: var(--accent);
		border: none;
		border-radius: 0.5rem;
		color: white;
		font-size: 0.85rem;
		cursor: pointer;
		white-space: nowrap;
	}

	.feed-item button:hover,
	.feed-item button:active {
		background: var(--accent-hover);
	}

	@media (max-width: 768px) {
		.feed-item {
			flex-direction: column;
		}

		.feed-item button {
			width: 100%;
		}
	}
</style>
