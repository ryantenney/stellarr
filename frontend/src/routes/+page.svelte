<script>
	import { onMount } from 'svelte';
	import { authenticated, loading, addToast } from '$lib/stores.js';
	import { verifyPassword, search, getTrending, addRequest } from '$lib/api.js';

	let password = '';
	let searchQuery = '';
	let searchResults = [];
	let trendingResults = [];
	let mediaFilter = 'all';
	let searchTimeout;

	onMount(async () => {
		if ($authenticated) {
			await loadTrending();
		}
	});

	async function handleLogin() {
		try {
			$loading = true;
			await verifyPassword(password);
			$authenticated = true;
			addToast('Welcome to Overseer Lite!', 'success');
			await loadTrending();
		} catch (error) {
			addToast('Invalid password', 'error');
		} finally {
			$loading = false;
		}
	}

	async function loadTrending() {
		try {
			const data = await getTrending(mediaFilter === 'all' ? 'all' : mediaFilter);
			trendingResults = data.results;
		} catch (error) {
			console.error('Failed to load trending:', error);
		}
	}

	async function handleSearch() {
		if (!searchQuery.trim()) {
			searchResults = [];
			return;
		}

		try {
			$loading = true;
			const filterType = mediaFilter === 'all' ? null : mediaFilter;
			const data = await search(searchQuery, filterType);
			searchResults = data.results;
		} catch (error) {
			addToast('Search failed', 'error');
		} finally {
			$loading = false;
		}
	}

	function debounceSearch() {
		clearTimeout(searchTimeout);
		searchTimeout = setTimeout(handleSearch, 300);
	}

	async function handleRequest(item) {
		try {
			await addRequest(item.id, item.media_type);
			item.requested = true;
			searchResults = [...searchResults];
			trendingResults = [...trendingResults];
			addToast(`Added "${item.title}" to requests`, 'success');
		} catch (error) {
			addToast('Failed to add request', 'error');
		}
	}

	function getPosterUrl(path) {
		if (!path) return 'https://via.placeholder.com/200x300?text=No+Image';
		return `https://image.tmdb.org/t/p/w200${path}`;
	}

	$: displayResults = searchQuery.trim() ? searchResults : trendingResults;
	$: sectionTitle = searchQuery.trim() ? 'Search Results' : 'Trending';
</script>

{#if !$authenticated}
	<div class="login-container">
		<div class="login-card">
			<h1>🎬 Overseer Lite</h1>
			<p>Enter the password to continue</p>
			<form on:submit|preventDefault={handleLogin}>
				<input
					type="password"
					bind:value={password}
					placeholder="Password"
					autocomplete="current-password"
				/>
				<button type="submit" disabled={$loading}>
					{$loading ? 'Checking...' : 'Enter'}
				</button>
			</form>
		</div>
	</div>
{:else}
	<div class="search-container">
		<div class="search-box">
			<input
				type="text"
				bind:value={searchQuery}
				on:input={debounceSearch}
				placeholder="Search for movies or TV shows..."
			/>
			<div class="filter-buttons">
				<button
					class:active={mediaFilter === 'all'}
					on:click={() => { mediaFilter = 'all'; handleSearch(); loadTrending(); }}
				>
					All
				</button>
				<button
					class:active={mediaFilter === 'movie'}
					on:click={() => { mediaFilter = 'movie'; handleSearch(); loadTrending(); }}
				>
					Movies
				</button>
				<button
					class:active={mediaFilter === 'tv'}
					on:click={() => { mediaFilter = 'tv'; handleSearch(); loadTrending(); }}
				>
					TV Shows
				</button>
			</div>
		</div>
	</div>

	<section class="results-section">
		<h2>{sectionTitle}</h2>
		{#if $loading}
			<div class="loading">Loading...</div>
		{:else if displayResults.length === 0}
			<p class="no-results">No results found</p>
		{:else}
			<div class="media-grid">
				{#each displayResults as item (item.id + item.media_type)}
					<div class="media-card">
						<div class="poster">
							<img src={getPosterUrl(item.poster_path)} alt={item.title} />
							<div class="media-type-badge">{item.media_type === 'tv' ? 'TV' : 'Movie'}</div>
							{#if item.vote_average}
								<div class="rating-badge">{item.vote_average.toFixed(1)}</div>
							{/if}
						</div>
						<div class="info">
							<h3 title={item.title}>{item.title}</h3>
							<span class="year">{item.year || 'Unknown'}</span>
							<p class="overview">{item.overview || 'No description available'}</p>
							<button
								class="request-btn"
								class:requested={item.requested}
								on:click={() => handleRequest(item)}
								disabled={item.requested}
							>
								{item.requested ? '✓ Requested' : '+ Request'}
							</button>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</section>
{/if}

<style>
	.login-container {
		display: flex;
		justify-content: center;
		align-items: center;
		min-height: 60vh;
	}

	.login-card {
		background: var(--bg-secondary);
		padding: 3rem;
		border-radius: 1rem;
		text-align: center;
		max-width: 400px;
		width: 100%;
	}

	.login-card h1 {
		margin-bottom: 0.5rem;
	}

	.login-card p {
		color: var(--text-secondary);
		margin-bottom: 2rem;
	}

	.login-card form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.login-card input {
		padding: 1rem;
		border: 1px solid var(--border);
		border-radius: 0.5rem;
		background: var(--bg-tertiary);
		color: var(--text-primary);
		font-size: 1rem;
	}

	.login-card button {
		padding: 1rem;
		background: var(--accent);
		border: none;
		border-radius: 0.5rem;
		color: white;
		font-size: 1rem;
		cursor: pointer;
		transition: background 0.2s;
	}

	.login-card button:hover:not(:disabled) {
		background: var(--accent-hover);
	}

	.login-card button:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.search-container {
		margin-bottom: 2rem;
	}

	.search-box {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.search-box input {
		padding: 1rem 1.5rem;
		border: 1px solid var(--border);
		border-radius: 0.75rem;
		background: var(--bg-secondary);
		color: var(--text-primary);
		font-size: 1.1rem;
		width: 100%;
	}

	.search-box input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.filter-buttons {
		display: flex;
		gap: 0.5rem;
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

	.results-section h2 {
		margin-bottom: 1.5rem;
		color: var(--text-primary);
	}

	.loading, .no-results {
		text-align: center;
		color: var(--text-secondary);
		padding: 3rem;
	}

	.media-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
		gap: 1.5rem;
	}

	.media-card {
		background: var(--bg-secondary);
		border-radius: 0.75rem;
		overflow: hidden;
		transition: transform 0.2s, box-shadow 0.2s;
	}

	.media-card:hover {
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

	.rating-badge {
		position: absolute;
		top: 0.5rem;
		right: 0.5rem;
		background: rgba(0, 0, 0, 0.8);
		padding: 0.25rem 0.5rem;
		border-radius: 0.25rem;
		font-size: 0.75rem;
		font-weight: 600;
		color: #ffd700;
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
		-webkit-line-clamp: 3;
		-webkit-box-orient: vertical;
		overflow: hidden;
		line-height: 1.4;
	}

	.request-btn {
		width: 100%;
		padding: 0.6rem;
		border: none;
		border-radius: 0.5rem;
		background: var(--accent);
		color: white;
		font-size: 0.9rem;
		cursor: pointer;
		transition: all 0.2s;
	}

	.request-btn:hover:not(:disabled) {
		background: var(--accent-hover);
	}

	.request-btn.requested {
		background: var(--success);
		cursor: default;
	}

	.request-btn:disabled {
		opacity: 0.8;
	}

	@media (max-width: 768px) {
		.media-grid {
			grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
			gap: 1rem;
		}
	}
</style>
