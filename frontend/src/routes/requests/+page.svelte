<script>
	import { onMount } from 'svelte';
	import { authenticated, loading, addToast } from '$lib/stores.js';
	import { getRequests, removeRequest } from '$lib/api.js';
	import { goto } from '$app/navigation';

	let requests = [];
	let mediaFilter = 'all';

	onMount(async () => {
		if (!$authenticated) {
			goto('/');
			return;
		}
		await loadRequests();
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

	function getRssUrl(type) {
		const base = window.location.origin;
		switch (type) {
			case 'movies':
				return `${base}/rss/movies`;
			case 'tv':
				return `${base}/rss/tv`;
			default:
				return `${base}/rss/all`;
		}
	}

	function copyRssUrl(type) {
		navigator.clipboard.writeText(getRssUrl(type));
		addToast('RSS URL copied to clipboard', 'success');
	}
</script>

{#if $authenticated}
	<div class="requests-page">
		<div class="header">
			<h1>My Requests</h1>
			<div class="rss-links">
				<h3>RSS Feeds</h3>
				<div class="rss-buttons">
					<button on:click={() => copyRssUrl('movies')} title="Copy Movies RSS URL">
						🎬 Movies RSS
					</button>
					<button on:click={() => copyRssUrl('tv')} title="Copy TV RSS URL">
						📺 TV RSS
					</button>
					<button on:click={() => copyRssUrl('all')} title="Copy All RSS URL">
						📋 All RSS
					</button>
				</div>
			</div>
		</div>

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
					<div class="request-card">
						<div class="poster">
							<img src={getPosterUrl(item.poster_path)} alt={item.title} />
							<div class="media-type-badge">{item.media_type === 'tv' ? 'TV' : 'Movie'}</div>
						</div>
						<div class="info">
							<h3 title={item.title}>{item.title}</h3>
							<span class="year">{item.year || 'Unknown'}</span>
							<p class="overview">{item.overview || 'No description available'}</p>
							<div class="meta">
								<span class="date">Added: {formatDate(item.created_at)}</span>
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
{/if}

<style>
	.requests-page {
		max-width: 1400px;
	}

	.header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		flex-wrap: wrap;
		gap: 1.5rem;
		margin-bottom: 2rem;
	}

	.header h1 {
		margin: 0;
	}

	.rss-links h3 {
		font-size: 0.9rem;
		color: var(--text-secondary);
		margin-bottom: 0.5rem;
	}

	.rss-buttons {
		display: flex;
		gap: 0.5rem;
	}

	.rss-buttons button {
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 0.5rem;
		background: var(--bg-tertiary);
		color: var(--text-secondary);
		cursor: pointer;
		font-size: 0.85rem;
		transition: all 0.2s;
	}

	.rss-buttons button:hover {
		border-color: var(--accent);
		color: var(--accent);
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

	@media (max-width: 768px) {
		.header {
			flex-direction: column;
		}

		.rss-buttons {
			flex-wrap: wrap;
		}

		.requests-grid {
			grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
			gap: 1rem;
		}
	}
</style>
