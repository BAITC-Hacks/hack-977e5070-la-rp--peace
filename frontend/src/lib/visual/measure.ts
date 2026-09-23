import type { Box, RowLayout } from './arrows';

/** Box of `element` relative to the top-left corner of `origin`. */
function boxIn(element: Element, origin: DOMRect): Box {
	const rect = element.getBoundingClientRect();
	return {
		left: rect.left - origin.left,
		top: rect.top - origin.top,
		right: rect.right - origin.left,
		bottom: rect.bottom - origin.top
	};
}

function boxesBy(row: HTMLElement, attribute: string, origin: DOMRect): Map<string, Box> {
	const boxes = new Map<string, Box>();
	for (const element of row.querySelectorAll<HTMLElement>(`[${attribute}]`)) {
		const id = element.getAttribute(attribute);
		if (id !== null) {
			boxes.set(id, boxIn(element, origin));
		}
	}
	return boxes;
}

/**
 * Measures a rendered block row: the columns are marked `data-column="before|after"`, cards
 * `data-finding="<id>"` and column items `data-item="<id>"`. Null until both columns exist.
 */
export function measureRow(row: HTMLElement): RowLayout | null {
	const before = row.querySelector('[data-column="before"]');
	const after = row.querySelector('[data-column="after"]');
	if (before === null || after === null) {
		return null;
	}
	const origin = row.getBoundingClientRect();
	return {
		before: boxIn(before, origin),
		after: boxIn(after, origin),
		cards: boxesBy(row, 'data-finding', origin),
		items: boxesBy(row, 'data-item', origin)
	};
}
