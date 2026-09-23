/** How long a flashed item stays highlighted, as in docs/spec/visual_compare.html. */
const FLASH_MS = 1600;

/**
 * Scrolls a column item of the visual comparison into view and briefly highlights it, e.g. after
 * a quote in the evidence panel was clicked. Does nothing if the item is not on the page.
 */
export function flashItem(itemId: string): void {
	const element = document.querySelector<HTMLElement>(`[data-item="${CSS.escape(itemId)}"]`);
	if (element === null) {
		return;
	}
	const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
	element.scrollIntoView({ block: 'center', behavior: calm ? 'auto' : 'smooth' });
	const tokens = getComputedStyle(document.documentElement);
	const highlight = tokens.getPropertyValue('--hl').trim();
	const accent = tokens.getPropertyValue('--accent').trim();
	element.animate(
		[
			{ backgroundColor: highlight, boxShadow: `0 0 0 2px ${accent}`, offset: 0 },
			{ backgroundColor: highlight, boxShadow: `0 0 0 2px ${accent}`, offset: 0.4 },
			{ backgroundColor: 'transparent', boxShadow: '0 0 0 2px transparent', offset: 1 }
		],
		{ duration: FLASH_MS, easing: 'ease-out' }
	);
}
