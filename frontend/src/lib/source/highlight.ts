/** A source context cut around the cited words, for rendering the quote highlighted. */
export interface ContextParts {
	before: string;
	quote: string;
	after: string;
}

/**
 * Splits `context` into the text before the quote, the quote and the text after it.
 *
 * `start` and `end` come from the backend, where Python counts code points, so the text is
 * cut by code points too — a UTF-16 index would drift after any character outside the BMP.
 * Offsets that do not describe a span of `context` highlight nothing: marking the wrong words
 * as the quote would be worse than marking none.
 */
export function splitContext(context: string, start: number, end: number): ContextParts {
	const chars = Array.from(context);
	const valid =
		Number.isInteger(start) &&
		Number.isInteger(end) &&
		start >= 0 &&
		start <= end &&
		end <= chars.length;
	if (!valid) {
		return { before: context, quote: '', after: '' };
	}
	return {
		before: chars.slice(0, start).join(''),
		quote: chars.slice(start, end).join(''),
		after: chars.slice(end).join('')
	};
}
