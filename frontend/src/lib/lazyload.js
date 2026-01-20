/**
 * Svelte action for lazy loading images with IntersectionObserver.
 * Only loads the image when it enters (or is about to enter) the viewport.
 *
 * Usage: <img use:lazyload={src} alt="..." />
 */
export function lazyload(node, src) {
	const observer = new IntersectionObserver(
		(entries) => {
			entries.forEach((entry) => {
				if (entry.isIntersecting) {
					node.src = src;
					observer.unobserve(node);
				}
			});
		},
		{
			rootMargin: '200px' // Start loading 200px before entering viewport
		}
	);

	observer.observe(node);

	return {
		update(newSrc) {
			src = newSrc;
			if (node.src !== newSrc) {
				node.src = newSrc;
			}
		},
		destroy() {
			observer.disconnect();
		}
	};
}
