<script>
	import { onMount } from 'svelte';
	import { authenticated, loading, addToast } from '$lib/stores.js';
	import { getRequests, removeRequest, getFeedInfo } from '$lib/api.js';
	import { goto } from '$app/navigation';

	let requests = [];
	let feedInfo = null;
	let mediaFilter = 'all';
	let showFeedModal = false;

	onMount(async () => {
		if (!$authenticated) {
			goto('/');
			return;
		}
		await Promise.all([loadRequests(), loadFeedInfo()]);
	});

	async function loadRequests() {
		try {
			$loading = true;
			const filterType = mediaFilter === 'all' ? null : mediaFilter;
			const data = await getRequests(filterType);
			requests = data.requests;
		} catch (error) {
			addToast('Failed to load requests', 'error');
		} finally {
			$loading = false;
		}
	}

	async function loadFeedInfo() {
		try {
			feedInfo = await getFeedInfo();
		} catch (error) {
			console.error('Failed to load feed info:', error);
		}
	}

	async function handleRemove(item) {
		if (!confirm(`Remove "${item.title}" from requests?`)) return;

		try {
			await removeRequest(item.tmdb_id, item.media_type);
			requests = requests.filter(r => !(r.tmdb_id === item.tmdb_id && r.media_type === item.media_type));
			addToast(`Removed "${item.title}"`, 'success');
		} catch (error) {
			addToast('Failed to remove request', 'error');
		}
	}

	function getPosterUrl(path) {
		if (!path) return 'https://via.placeholder.com/200x300?text=No+Image';
		return `https://image.tmdb.org/t/p/w200${path}`;
	}

	function formatDate(dateStr) {
		if (!dateStr) return '';
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-US', {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	}

	function copyUrl(url) {
		navigator.clipboard.writeText(url);
		addToast('URL copied to clipboard', 'success');
	}

	function getMissingIdWarning(item) {
		if (item.media_type === 'movie' && !item.imdb_id) {
			return 'Missing IMDB ID - will not appear in Radarr feed';
		}
		if (item.media_type === 'tv' && !item.tvdb_id) {
			return 'Missing TVDB ID - will not appear in Sonarr feed';
		}
		return null;
	}

	$: itemsWithMissingIds = requests.filter(r =>
		(r.media_type === 'movie' && !r.imdb_id) ||
		(r.media_type === 'tv' && !r.tvdb_id)
	);
</script>

{#if $authenticated}
	<div class="requests-page">
		<div class="header">
			<h1>My Requests</h1>
			<button class="feeds-btn" on:click={() => showFeedModal = true}>
				Feed URLs
			</button>
		</div>

		{#if itemsWithMissingIds.length > 0}
			<div class="warning-banner">
				<strong>Warning:</strong> {itemsWithMissingIds.length} item{itemsWithMissingIds.length > 1 ? 's' : ''} missing external IDs and won't appear in Sonarr/Radarr feeds.
			</div>
		{/if}

		<div class="filter-buttons">
			<button
				class:active={mediaFilter === 'all'}
				on:click={() => { mediaFilter = 'all'; loadRequests(); }}
			>
				All ({requests.length})
			</button>
			<button
				class:active={mediaFilter === 'movie'}
				on:click={() => { mediaFilter = 'movie'; loadRequests(); }}
			>
				Movies
			</button>
			<button
				class:active={mediaFilter === 'tv'}
				on:click={() => { mediaFilter = 'tv'; loadRequests(); }}
			>
				TV Shows
			</button>
		</div>

		{#if $loading}
			<div class="loading">Loading...</div>
		{:else if requests.length === 0}
			<div class="empty-state">
				<p>No requests yet</p>
				<a href="/">Browse and add some!</a>
			</div>
		{:else}
			<div class="requests-grid">
				{#each requests as item (item.id)}
					<div class="request-card" class:has-warning={getMissingIdWarning(item)}>
						<div class="poster">
							<img src={getPosterUrl(item.poster_path)} alt={item.title} />
							<div class="media-type-badge">{item.media_type === 'tv' ? 'TV' : 'Movie'}</div>
							{#if getMissingIdWarning(item)}
								<div class="warning-badge" title={getMissingIdWarning(item)}>!</div>
							{/if}
						</div>
						<div class="info">
							<h3 title={item.title}>{item.title}</h3>
							<span class="year">{item.year || 'Unknown'}</span>
							<p class="overview">{item.overview || 'No description available'}</p>
							<div class="meta">
								<span class="date">
									{#if item.requested_by}
										{item.requested_by} · {formatDate(item.created_at)}
									{:else}
										Added: {formatDate(item.created_at)}
									{/if}
								</span>
								{#if item.imdb_id}
									<a
										href="https://www.imdb.com/title/{item.imdb_id}"
										target="_blank"
										rel="noopener"
										class="imdb-link"
									>
										IMDb
									</a>
								{/if}
							</div>
							<button
								class="remove-btn"
								on:click={() => handleRemove(item)}
							>
								Remove
							</button>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Feed URLs Modal -->
	{#if showFeedModal && feedInfo}
		<div class="modal-overlay" on:click={() => showFeedModal = false}>
			<div class="modal" on:click|stopPropagation>
				<div class="modal-header">
					<h2>Feed URLs for Sonarr/Radarr</h2>
					<button class="close-btn" on:click={() => showFeedModal = false}>&times;</button>
				</div>
				<div class="modal-content">
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
				</div>
			</div>
		</div>
	{/if}
{/if}

<style>
	.requests-page {
		max-width: 1400px;
	}

	.header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 2rem;
	}

	.header h1 {
		margin: 0;
	}

	.feeds-btn {
		padding: 0.75rem 1.5rem;
		background: var(--accent);
		border: none;
		border-radius: 0.5rem;
		color: white;
		font-size: 1rem;
		cursor: pointer;
		transition: background 0.2s;
	}

	.feeds-btn:hover {
		background: var(--accent-hover);
	}

	.warning-banner {
		background: rgba(245, 158, 11, 0.15);
		border: 1px solid var(--warning);
		color: var(--warning);
		padding: 0.75rem 1rem;
		border-radius: 0.5rem;
		margin-bottom: 1.5rem;
		font-size: 0.9rem;
	}

	.filter-buttons {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 1.5rem;
	}

	.filter-buttons button {
		padding: 0.5rem 1rem;
		border: 1px solid var(--border);
		border-radius: 0.5rem;
		background: transparent;
		color: var(--text-secondary);
		cursor: pointer;
		transition: all 0.2s;
	}

	.filter-buttons button:hover {
		border-color: var(--accent);
		color: var(--accent);
	}

	.filter-buttons button.active {
		background: var(--accent);
		border-color: var(--accent);
		color: white;
	}

	.loading, .empty-state {
		text-align: center;
		color: var(--text-secondary);
		padding: 3rem;
	}

	.empty-state a {
		color: var(--accent);
		text-decoration: none;
	}

	.empty-state a:hover {
		text-decoration: underline;
	}

	.requests-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
		gap: 1.5rem;
	}

	.request-card {
		background: var(--bg-secondary);
		border-radius: 0.75rem;
		overflow: hidden;
		transition: transform 0.2s, box-shadow 0.2s;
	}

	.request-card:hover {
		transform: translateY(-4px);
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
	}

	.poster {
		position: relative;
		aspect-ratio: 2/3;
	}

	.poster img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	.media-type-badge {
		position: absolute;
		top: 0.5rem;
		left: 0.5rem;
		background: var(--accent);
		padding: 0.25rem 0.5rem;
		border-radius: 0.25rem;
		font-size: 0.75rem;
		font-weight: 600;
	}

	.warning-badge {
		position: absolute;
		top: 0.5rem;
		right: 0.5rem;
		background: var(--warning);
		color: black;
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: 700;
		font-size: 1rem;
		cursor: help;
	}

	.request-card.has-warning {
		border: 1px solid var(--warning);
	}

	.info {
		padding: 1rem;
	}

	.info h3 {
		font-size: 0.95rem;
		margin-bottom: 0.25rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.year {
		color: var(--text-secondary);
		font-size: 0.85rem;
	}

	.overview {
		font-size: 0.8rem;
		color: var(--text-secondary);
		margin: 0.75rem 0;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		line-height: 1.4;
	}

	.meta {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.75rem;
		font-size: 0.75rem;
	}

	.date {
		color: var(--text-secondary);
	}

	.imdb-link {
		color: #f5c518;
		text-decoration: none;
		font-weight: 600;
	}

	.imdb-link:hover {
		text-decoration: underline;
	}

	.remove-btn {
		width: 100%;
		padding: 0.6rem;
		border: 1px solid var(--error);
		border-radius: 0.5rem;
		background: transparent;
		color: var(--error);
		font-size: 0.9rem;
		cursor: pointer;
		transition: all 0.2s;
	}

	.remove-btn:hover {
		background: var(--error);
		color: white;
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
		max-height: 90vh;
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
	}

	.close-btn:hover {
		color: var(--text-primary);
	}

	.modal-content {
		padding: 1.5rem;
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

	.feed-item button:hover {
		background: var(--accent-hover);
	}

	@media (max-width: 768px) {
		.header {
			flex-direction: column;
			align-items: flex-start;
			gap: 1rem;
		}

		.requests-grid {
			grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
			gap: 1rem;
		}

		.feed-item {
			flex-direction: column;
		}

		.feed-item button {
			width: 100%;
		}
	}
</style>
