import type { DocSet } from '$lib/api/types';
import { DOC_SETS } from '$lib/documents';

import type { UploadItem } from './session.svelte';

/** A document of the upload screen whose parse has ended, so its structure can be opened. */
export interface ParsedDocument {
	id: number;
	set: DocSet;
	name: string;
}

const SET_ORDER = DOC_SETS.map((info) => info.set);

/** Parsed documents: «До» first, then «После», then the external sets, each in upload order. */
export function parsedDocuments(
	items: readonly Pick<UploadItem, 'set' | 'name' | 'document' | 'parsed'>[]
): ParsedDocument[] {
	return SET_ORDER.flatMap((set) =>
		items.flatMap((item) =>
			item.set === set && item.parsed && item.document !== null
				? [{ id: item.document.id, set, name: item.name }]
				: []
		)
	);
}

/** The first parsed «До» and «После» documents, which the Word view compares; null without both. */
export function comparePair(
	documents: readonly ParsedDocument[]
): { before: number; after: number } | null {
	const before = documents.find((doc) => doc.set === 'before');
	const after = documents.find((doc) => doc.set === 'after');
	return before === undefined || after === undefined
		? null
		: { before: before.id, after: after.id };
}
