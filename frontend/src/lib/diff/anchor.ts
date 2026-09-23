import { parseDocumentId } from '$lib/document/view.svelte';

/**
 * The Word view lives at `/compare?before=<id>&after=<id>`; `#node-<id>` (a node of either
 * document) opens it scrolled to that node, highlighted — the jump from a quote.
 */
export interface CompareParams {
	before: number | null;
	after: number | null;
}

export function parseCompareParams(search: URLSearchParams): CompareParams {
	return {
		before: parseDocumentId(search.get('before') ?? ''),
		after: parseDocumentId(search.get('after') ?? '')
	};
}

/** DOM id of the element standing for a node in the Word view. */
export function nodeAnchorId(nodeId: number): string {
	return `node-${nodeId}`;
}

/** Node id from a location hash such as `#node-12`, or null for any other hash. */
export function parseNodeHash(hash: string): number | null {
	const match = /^#node-(\d+)$/.exec(hash);
	return match === null ? null : parseDocumentId(match[1]);
}
