<script>
	import { onMount, onDestroy } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { authenticated, loading, addToast, removeFromRequestsOptimistic } from '$lib/stores.js';
	import { getRequests, removeRequest } from '$lib/api.js';
	import { lazyload } from '$lib/lazyload.js';
	import { goto } from '$app/navigation';

	let requests = [];
	let mediaFilter = 'all';
	let statusFilter = 'pending'; // 'all', 'pending', 'added'
	let showConfirmModal = false;
	let itemToRemove = null;
	let removing = false;

	// Pagination - target ~20-24 items per page
	let currentPage = 1;
	let gridContainer;
	let columnCount = 5;
	const targetItemsPerPage = 24;
	$: itemsPerPage = targetItemsPerPage;
	$: rowsPerPage = Math.ceil(targetItemsPerPage / columnCount);

	function updateColumnCount() {
		if (!gridContainer) return;
		const containerWidth = gridContainer.offsetWidth;
		const gap = 24; // 1.5rem gap
		const minCardWidth = 180;
		// Calculate how many columns fit
		columnCount = Math.max(1, Math.floor((containerWidth + gap) / (minCardWidth + gap)));
	}

	let resizeObserver;

	// Computed: filtered by status (client-side)
	$: filteredByStatus = statusFilter === 'all'
		? requests
		: statusFilter === 'added'
			? requests.filter(r => r.added_at).sort((a, b) => new Date(b.added_at) - new Date(a.added_at))
			: requests.filter(r => !r.added_at);

	// Computed: pagination
	$: totalPages = Math.ceil(filteredByStatus.length / itemsPerPage);
	$: paginatedItems = filteredByStatus.slice(
		(currentPage - 1) * itemsPerPage,
		currentPage * itemsPerPage
	);

	// Reset page when filters change
	$: if (mediaFilter || statusFilter) currentPage = 1;

	// Counts for filter buttons
	$: pendingCount = requests.filter(r => !r.added_at).length;
	$: addedCount = requests.filter(r => r.added_at).length;

	onMount(async () => {
		if (!$authenticated) {
			goto('/');
			return;
		}
		await loadRequests();
	});

	// Set up resize observer when grid container becomes available
	$: if (gridContainer && !resizeObserver) {
		updateColumnCount();
		resizeObserver = new ResizeObserver(() => {
			updateColumnCount();
		});
		resizeObserver.observe(gridContainer);
	}

	onDestroy(() => {
		if (resizeObserver) {
			resizeObserver.disconnect();
		}
	});

	async function loadRequests() {
		try {
			$loading = true;
			const filterType = mediaFilter === 'all' ? null : mediaFilter;
			const data = await getRequests(filterType);
			requests = data.requests;
		} catch (error) {
			addToast($_('requests.failedToLoad'), 'error');
		} finally {
			$loading = false;
		}
	}

	function handleRemove(item) {
		itemToRemove = item;
		showConfirmModal = true;
	}

	function cancelRemove() {
		showConfirmModal = false;
		itemToRemove = null;
	}

	async function confirmRemove() {
		if (!itemToRemove || removing) return;

		removing = true;
		const tmdbId = Number(itemToRemove.tmdb_id);
		const mediaType = itemToRemove.media_type;
		const title = itemToRemove.title;

		// Optimistic update - remove from both local and global store immediately
		requests = requests.filter(r => !(Number(r.tmdb_id) === tmdbId && r.media_type === mediaType));
		removeFromRequestsOptimistic(tmdbId, mediaType);
		showConfirmModal = false;

		try {
			await removeRequest(tmdbId, mediaType);
			addToast($_('requests.removed', { values: { title } }), 'success');
		} catch (error) {
			// Revert on failure by reloading
			addToast($_('removeModal.failed'), 'error');
			await loadRequests();
		} finally {
			removing = false;
			itemToRemove = null;
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

	function getMissingIdWarning(item) {
		if (item.media_type === 'movie' && !item.imdb_id) {
			return $_('requestsWarning.missingImdb');
		}
		if (item.media_type === 'tv' && !item.tvdb_id) {
			return $_('requestsWarning.missingTvdb');
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
		<h1>{$_('requests.title')}</h1>

		{#if itemsWithMissingIds.length > 0}
			<div class="warning-banner">
				<strong>{$_('requestsWarning.title')}</strong> {$_('requestsWarning.missingIds', { values: { count: itemsWithMissingIds.length } })}
			</div>
		{/if}

		<div class="filters-row">
			<div class="filter-buttons">
				<button
					class:active={mediaFilter === 'all'}
					on:click={() => { mediaFilter = 'all'; loadRequests(); }}
				>
					{$_('filters.all')} ({requests.length})
				</button>
				<button
					class:active={mediaFilter === 'movie'}
					on:click={() => { mediaFilter = 'movie'; loadRequests(); }}
				>
					{$_('filters.movies')}
				</button>
				<button
					class:active={mediaFilter === 'tv'}
					on:click={() => { mediaFilter = 'tv'; loadRequests(); }}
				>
					{$_('filters.tvShows')}
				</button>
			</div>

			<div class="filter-buttons status-filter">
				<button
					class:active={statusFilter === 'all'}
					on:click={() => statusFilter = 'all'}
				>
					{$_('requests.allStatus')}
				</button>
				<button
					class:active={statusFilter === 'pending'}
					on:click={() => statusFilter = 'pending'}
				>
					{$_('requests.pending')} ({pendingCount})
				</button>
				<button
					class:active={statusFilter === 'added'}
					on:click={() => statusFilter = 'added'}
				>
					{$_('requests.added')} ({addedCount})
				</button>
			</div>
		</div>

		<div class="grid-wrapper" bind:this={gridContainer}>
		{#if $loading}
			<div class="loading">{$_('search.loading')}</div>
		{:else if requests.length === 0}
			<div class="empty-state">
				<p>{$_('requests.noRequests')}</p>
				<a href="/">{$_('requests.browseAndAdd')}</a>
			</div>
		{:else if filteredByStatus.length === 0}
			<div class="empty-state">
				<p>{statusFilter === 'pending' ? $_('requests.noPending') : $_('requests.noAdded')}</p>
			</div>
		{:else}
			<div class="requests-grid">
				{#each paginatedItems as item (`${item.media_type}-${item.tmdb_id}`)}
					<div class="request-card" class:has-warning={getMissingIdWarning(item)} class:is-added={item.added_at}>
						<div class="poster">
							<img use:lazyload={getPosterUrl(item.poster_path)} alt={item.title} />
							<div class="media-type-badge">{item.media_type === 'tv' ? $_('media.tv') : $_('media.movie')}</div>
							{#if item.added_at}
								<div class="status-badge in-library" title="{$_('dates.added', { values: { date: formatDate(item.added_at) } })}">{$_('media.inLibrary')}</div>
							{:else}
								<div class="status-badge requested">{$_('media.requested')}</div>
							{/if}
							{#if getMissingIdWarning(item) && !item.added_at}
								<div class="warning-badge" title={getMissingIdWarning(item)}>!</div>
							{/if}
							<button
								class="remove-icon"
								on:click={() => handleRemove(item)}
								title={$_('requests.removeRequest')}
							>×</button>
						</div>
						<div class="info">
							<h3 title={item.title}>{item.title}</h3>
							<span class="year">{item.year || $_('media.unknown')}</span>
							<p class="overview">{item.overview || $_('media.noDescription')}</p>
							<div class="meta">
								<span class="date">
									{#if item.added_at}
										{$_('dates.added', { values: { date: formatDate(item.added_at) } })}
									{:else if item.requested_by}
										{item.requested_by} · {formatDate(item.created_at)}
									{:else}
										{$_('dates.requested', { values: { date: formatDate(item.created_at) } })}
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
						{$_('pagination.previous')}
					</button>
					<span>{$_('pagination.pageOf', { values: { current: currentPage, total: totalPages } })}</span>
					<button
						disabled={currentPage === totalPages}
						on:click={() => currentPage++}
					>
						{$_('pagination.next')}
					</button>
				</div>
			{/if}
		{/if}
		</div>
	</div>

	<!-- Confirm Remove Modal -->
	{#if showConfirmModal && itemToRemove}
		<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
		<div class="modal-overlay" on:click={cancelRemove}>
			<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
			<div class="modal confirm-modal" on:click|stopPropagation>
				<div class="confirm-content">
					<img src={getPosterUrl(itemToRemove.poster_path)} alt={itemToRemove.title} class="confirm-poster" />
					<div class="confirm-text">
						<h2>{$_('removeModal.title')}</h2>
						<p>{$_('removeModal.confirm', { values: { title: itemToRemove.title } })}</p>
					</div>
				</div>
				<div class="confirm-actions">
					<button class="cancel-btn" on:click={cancelRemove} disabled={removing}>{$_('removeModal.cancel')}</button>
					<button class="confirm-btn" on:click={confirmRemove} disabled={removing}>
						{removing ? $_('removeModal.removing') : $_('removeModal.remove')}
					</button>
				</div>
			</div>
		</div>
	{/if}

{/if}

<style>
	.requests-page {
		max-width: 1400px;
	}

	h1 {
		margin-bottom: 1.5rem;
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

	.filters-row {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		margin-bottom: 1.5rem;
		align-items: center;
	}

	.filter-buttons {
		display: flex;
		gap: 0.5rem;
	}

	.status-filter {
		margin-left: auto;
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
		transition: box-shadow 0.2s;
	}

	.request-card:hover {
		box-shadow: 0 0 0 2px var(--accent);
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

	.status-badge {
		position: absolute;
		bottom: 0.5rem;
		left: 0.5rem;
		padding: 0.25rem 0.5rem;
		border-radius: 0.25rem;
		font-size: 0.7rem;
		font-weight: 600;
		color: white;
	}

	.status-badge.requested {
		background: rgba(100, 100, 100, 0.9);
	}

	.status-badge.in-library {
		background: rgba(76, 175, 80, 0.9);
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

	.remove-icon {
		position: absolute;
		top: 0.25rem;
		right: 0.25rem;
		width: 1.5rem;
		height: 1.5rem;
		border: none;
		border-radius: 50%;
		background: rgba(0, 0, 0, 0.6);
		color: white;
		font-size: 1.1rem;
		line-height: 1;
		cursor: pointer;
		opacity: 0;
		transition: opacity 0.2s, background 0.2s;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.request-card:hover .remove-icon {
		opacity: 1;
	}

	.remove-icon:hover {
		background: var(--error);
	}

	.request-card.has-warning:not(.is-added) {
		border: 1px solid var(--warning);
	}

	.request-card.is-added {
		opacity: 0.85;
	}

	.request-card.is-added .poster::after {
		content: '';
		position: absolute;
		inset: 0;
		background: linear-gradient(to bottom, rgba(16, 185, 129, 0.1), transparent);
		pointer-events: none;
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

	/* Confirm Modal */
	.confirm-modal {
		max-width: 400px;
		padding: 1.5rem;
	}

	.confirm-content {
		display: flex;
		gap: 1rem;
		margin-bottom: 1.5rem;
	}

	.confirm-poster {
		width: 80px;
		height: 120px;
		object-fit: cover;
		border-radius: 0.5rem;
		flex-shrink: 0;
	}

	.confirm-text h2 {
		margin: 0 0 0.5rem 0;
		font-size: 1.25rem;
	}

	.confirm-text p {
		margin: 0;
		color: var(--text-secondary);
		font-size: 0.95rem;
		line-height: 1.5;
	}

	.confirm-actions {
		display: flex;
		gap: 0.75rem;
		justify-content: flex-end;
	}

	.cancel-btn {
		padding: 0.75rem 1.5rem;
		border: 1px solid var(--border);
		border-radius: 0.5rem;
		background: transparent;
		color: var(--text-secondary);
		font-size: 0.95rem;
		cursor: pointer;
		transition: all 0.2s;
	}

	.cancel-btn:hover:not(:disabled),
	.cancel-btn:active:not(:disabled) {
		border-color: var(--text-primary);
		color: var(--text-primary);
	}

	.confirm-btn {
		padding: 0.75rem 1.5rem;
		border: none;
		border-radius: 0.5rem;
		background: var(--error);
		color: white;
		font-size: 0.95rem;
		cursor: pointer;
		transition: all 0.2s;
	}

	.confirm-btn:hover:not(:disabled),
	.confirm-btn:active:not(:disabled) {
		background: #dc2626;
	}

	.confirm-btn:disabled,
	.cancel-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
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
		.filters-row {
			flex-direction: column;
			align-items: flex-start;
		}

		.status-filter {
			margin-left: 0;
		}

		.requests-grid {
			grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
			gap: 1rem;
		}
	}
</style>
