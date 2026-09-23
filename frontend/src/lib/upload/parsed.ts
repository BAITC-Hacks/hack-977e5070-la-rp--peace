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
	items: readonly Pick<UploadItem, 'set' | 'file' | 'document' | 'parsed'>[]
): ParsedDocument[] {
	return SET_ORDER.flatMap((set) =>
		items.flatMap((item) =>
			item.set === set && item.parsed && item.document !== null
				? [{ id: item.document.id, set, name: item.file.name }]
				: []
		)
	);
}
