<script>
	import { onMount, onDestroy } from 'svelte';
	import { authenticated, loading, addToast, setAuthenticated } from '$lib/stores.js';
	import { verifyPassword, search, getTrending, addRequest, getRequests, warmup } from '$lib/api.js';

	// Cache of requested items to hydrate cached trending results
	let requestedItems = new Set();

	let password = '';
	let userName = '';
	let searchQuery = '';
	let searchResults = [];
	let trendingResults = [];
	let mediaFilter = 'all';
	let searchTimeout = null;

	// Pagination - target ~20-24 items per page
	let currentPage = 1;
	let gridContainer;
	let columnCount = 5;
	const targetItemsPerPage = 24;
	$: itemsPerPage = targetItemsPerPage;
	$: rowsPerPage = Math.ceil(targetItemsPerPage / columnCount);
	$: totalPages = Math.ceil(displayResults.length / itemsPerPage);
	$: paginatedResults = displayResults.slice(
		(currentPage - 1) * itemsPerPage,
		currentPage * itemsPerPage
	);

	function updateColumnCount() {
		if (!gridContainer) return;
		const containerWidth = gridContainer.offsetWidth;
		const gap = 24; // 1.5rem gap
		const minCardWidth = 180;
		columnCount = Math.max(1, Math.floor((containerWidth + gap) / (minCardWidth + gap)));
	}

	let resizeObserver;

	// Handle PWA returning to foreground - warm up Lambda and refresh data
	function handleVisibilityChange() {
		if (document.visibilityState === 'visible' && $authenticated) {
			// Warm up Lambda in background (don't await)
			warmup();
			// Refresh request status to hydrate any cached data
			loadRequestedItems();
		}
	}

	onMount(async () => {
		// Listen for PWA being brought to foreground
		document.addEventListener('visibilitychange', handleVisibilityChange);

		if ($authenticated) {
			// Load requests first to hydrate cached trending data
			await loadRequestedItems();
			await loadTrending();
		}
	});

	async function loadRequestedItems() {
		try {
			const data = await getRequests();
			requestedItems = new Set(
				data.requests.map(r => `${r.media_type}:${r.tmdb_id}`)
			);
		} catch (error) {
			console.error('Failed to load requests:', error);
		}
	}

	function hydrateResults(results) {
		// Merge current request status into results (for cached data)
		return results.map(item => ({
			...item,
			requested: item.requested || requestedItems.has(`${item.media_type}:${item.id}`)
		}));
	}

	// Set up resize observer when grid container becomes available
	$: if (gridContainer && !resizeObserver) {
		updateColumnCount();
		resizeObserver = new ResizeObserver(() => {
			updateColumnCount();
		});
		resizeObserver.observe(gridContainer);
	}

	onDestroy(() => {
		document.removeEventListener('visibilitychange', handleVisibilityChange);
		if (resizeObserver) {
			resizeObserver.disconnect();
		}
		if (searchTimeout) {
			clearTimeout(searchTimeout);
		}
	});

	async function handleLogin() {
		if (!userName.trim()) {
			addToast('Please enter your name', 'error');
			return;
		}
		try {
			$loading = true;
			const response = await verifyPassword(password, userName.trim());
			setAuthenticated(response.token, response.name);
			addToast(`Welcome, ${response.name}!`, 'success');
			await loadTrending();
		} catch (error) {
			addToast(error.message || 'Invalid credentials', 'error');
		} finally {
			$loading = false;
		}
	}

	async function loadTrending() {
		try {
			const data = await getTrending(mediaFilter === 'all' ? 'all' : mediaFilter);
			trendingResults = hydrateResults(data.results);
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
			searchResults = hydrateResults(data.results);
		} catch (error) {
			addToast('Search failed', 'error');
		} finally {
			$loading = false;
		}
	}

	function debounceSearch() {
		if (searchTimeout) {
			clearTimeout(searchTimeout);
		}
		searchTimeout = setTimeout(() => {
			searchTimeout = null;
			handleSearch();
		}, 500);
	}

	async function handleRequest(item) {
		try {
			await addRequest(item.id, item.media_type);
			// Update local cache for future hydration
			requestedItems.add(`${item.media_type}:${item.id}`);
			item.requested = true;
			searchResults = [...searchResults];
			trendingResults = [...trendingResults];
			addToast(`Added "${item.title}" to requests`, 'success');
		} catch (error) {
			addToast('Failed to add request', 'error');
		}
	}

	function getPosterUrl(path) {
		if (!path) return null;
		return `https://image.tmdb.org/t/p/w200${path}`;
	}

	function handlePosterError(event) {
		// Hide broken image, show placeholder
		event.target.style.display = 'none';
	}

	$: displayResults = searchQuery.trim() ? searchResults : trendingResults;
	$: sectionTitle = searchQuery.trim() ? 'Search Results' : 'Trending';

	// Reset page when search/filter changes
	$: if (searchQuery || mediaFilter) currentPage = 1;
</script>

{#if !$authenticated}
	<div class="login-container">
		<div class="login-card">
			<h1>🎬 Overseer Lite</h1>
			<p>Enter your name and password to continue</p>
			<form on:submit|preventDefault={handleLogin}>
				<input
					type="text"
					bind:value={userName}
					placeholder="Your Name"
					autocomplete="name"
				/>
				<input
					type="password"
					bind:value={password}
					placeholder="Password"
					autocomplete="current-password"
				/>
				<button type="submit" disabled={$loading || !userName.trim()}>
					{$loading ? 'Checking...' : 'Enter'}
				</button>
			</form>
		</div>
	</div>
{:else}
	<div class="search-container">
		<div class="search-box">
			<div class="search-input-wrapper">
				<input
					type="search"
					bind:value={searchQuery}
					on:input={debounceSearch}
					on:keydown={(e) => { if (e.key === 'Enter') e.target.blur(); }}
					enterkeyhint="search"
					placeholder="Search for movies or TV shows..."
				/>
				{#if searchQuery}
					<button
						class="clear-btn"
						on:click={() => { searchQuery = ''; searchResults = []; }}
						aria-label="Clear search"
					>×</button>
				{/if}
			</div>
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
		<div class="grid-wrapper" bind:this={gridContainer}>
		{#if $loading}
			<div class="loading">Loading...</div>
		{:else if displayResults.length === 0}
			<p class="no-results">No results found</p>
		{:else}
			<div class="media-grid">
				{#each paginatedResults as item (item.id + item.media_type)}
					<div class="media-card">
						<div class="poster">
							<div class="poster-placeholder">
								<span class="placeholder-icon">🎬</span>
							</div>
							{#if getPosterUrl(item.poster_path)}
								<img
									src={getPosterUrl(item.poster_path)}
									alt={item.title}
									on:error={handlePosterError}
								/>
							{/if}
							<div class="media-type-badge">{item.media_type === 'tv' ? 'TV' : 'Movie'}</div>
							{#if item.vote_average}
								<div class="rating-badge">{item.vote_average.toFixed(1)}</div>
							{/if}
							{#if item.in_library}
								{#if item.media_type === 'movie' && item.imdb_id}
									<a href="https://www.imdb.com/title/{item.imdb_id}" target="_blank" rel="noopener" class="library-badge" title="View in IMDb">In Library</a>
								{:else if item.media_type === 'tv' && item.tvdb_id}
									<a href="https://thetvdb.com/series/{item.tvdb_id}" target="_blank" rel="noopener" class="library-badge" title="View in TheTVDB">In Library</a>
								{:else}
									<div class="library-badge" title="Already in Plex">In Library</div>
								{/if}
							{:else if item.number_of_seasons}
								{#if item.number_of_seasons > 10}
									<div class="seasons-warning seasons-very-large" title="Very large series - {item.number_of_seasons} seasons may take significant time to download">
										{item.number_of_seasons} Seasons
									</div>
								{:else if item.number_of_seasons > 6}
									<div class="seasons-warning" title="Large series - {item.number_of_seasons} seasons may take a while to download">
										{item.number_of_seasons} Seasons
									</div>
								{/if}
							{/if}
						</div>
						<div class="info">
							<h3 title={item.title}>{item.title}</h3>
							<span class="year">{item.year || 'Unknown'}</span>
							<p class="overview">{item.overview || 'No description available'}</p>
							<button
								class="request-btn"
								class:requested={item.requested}
								class:in-library={item.in_library}
								on:click={() => handleRequest(item)}
								disabled={item.requested || item.in_library}
							>
								{#if item.in_library}
									In Library
								{:else if item.requested}
									✓ Requested
								{:else}
									+ Request
								{/if}
							</button>
						</div>
					</div>
				{/each}
			</div>

			{#if totalPages > 1}
				<div class="pagination">
					<button
						disabled={currentPage === 1}
						on:click={() => currentPage--}
					>
						Previous
					</button>
					<span>Page {currentPage} of {totalPages}</span>
					<button
						disabled={currentPage === totalPages}
						on:click={() => currentPage++}
					>
						Next
					</button>
				</div>
			{/if}
		{/if}
		</div>
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

	.login-card button:hover:not(:disabled),
	.login-card button:active:not(:disabled) {
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

	.search-input-wrapper {
		position: relative;
		width: 100%;
	}

	.search-box input {
		padding: 1rem 2.5rem 1rem 1.5rem;
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

	/* Hide native search clear button (we have our own) */
	.search-box input[type="search"]::-webkit-search-cancel-button {
		-webkit-appearance: none;
		appearance: none;
	}

	.clear-btn {
		position: absolute;
		right: 0.25rem;
		top: 50%;
		transform: translateY(-50%);
		background: transparent;
		border: none;
		color: var(--text-secondary);
		font-size: 1.25rem;
		cursor: pointer;
		min-width: 44px;
		min-height: 44px;
		line-height: 1;
		border-radius: 50%;
		transition: color 0.2s, background 0.2s;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.clear-btn:hover,
	.clear-btn:active {
		color: var(--text-primary);
		background: var(--bg-tertiary);
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

	.filter-buttons button:hover,
	.filter-buttons button:active {
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
		transition: box-shadow 0.2s;
	}

	.media-card:hover {
		box-shadow: 0 0 0 2px var(--accent);
	}

	.poster {
		position: relative;
		aspect-ratio: 2/3;
	}

	.poster-placeholder {
		position: absolute;
		inset: 0;
		background: var(--bg-tertiary);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.placeholder-icon {
		font-size: 3rem;
		opacity: 0.4;
	}

	.poster img {
		position: absolute;
		inset: 0;
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

	.library-badge {
		position: absolute;
		bottom: 0.5rem;
		left: 0.5rem;
		background: rgba(76, 175, 80, 0.9);
		padding: 0.25rem 0.5rem;
		border-radius: 0.25rem;
		font-size: 0.7rem;
		font-weight: 600;
		color: white;
		text-decoration: none;
		display: inline-block;
		cursor: pointer;
		transition: background 0.2s;
	}

	.library-badge:hover {
		background: rgba(76, 175, 80, 1);
		text-decoration: underline;
	}

	.seasons-warning {
		position: absolute;
		bottom: 0.5rem;
		left: 0.5rem;
		background: rgba(245, 158, 11, 0.9);
		padding: 0.25rem 0.5rem;
		border-radius: 0.25rem;
		font-size: 0.7rem;
		font-weight: 600;
		color: white;
		cursor: help;
	}

	.seasons-warning.seasons-very-large {
		background: rgba(220, 38, 38, 0.9);
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

	.request-btn:hover:not(:disabled),
	.request-btn:active:not(:disabled) {
		background: var(--accent-hover);
	}

	.request-btn.requested {
		background: var(--bg-tertiary);
		color: var(--text-secondary);
		cursor: default;
	}

	.request-btn.in-library {
		background: var(--bg-tertiary);
		color: var(--text-secondary);
		cursor: default;
	}

	.request-btn:disabled {
		opacity: 0.8;
	}

	/* Pagination */
	.pagination {
		display: flex;
		justify-content: center;
		align-items: center;
		gap: 1rem;
		margin-top: 2rem;
		padding: 1rem;
	}

	.pagination button {
		padding: 0.5rem 1rem;
		border: 1px solid var(--border);
		border-radius: 0.5rem;
		background: transparent;
		color: var(--text-secondary);
		cursor: pointer;
		transition: all 0.2s;
	}

	.pagination button:hover:not(:disabled),
	.pagination button:active:not(:disabled) {
		border-color: var(--accent);
		color: var(--accent);
	}

	.pagination button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.pagination span {
		color: var(--text-secondary);
	}

	@media (max-width: 768px) {
		.media-grid {
			grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
			gap: 1rem;
		}
	}
</style>
