import { SET_LABELS } from '$lib/source/label';
import type { UploadItem } from '$lib/upload/session.svelte';

import type { DocumentProgress, StageId, StageState } from './stages';

/** What the status screen needs to know about one file of the upload screen. */
export type UploadProgress = Pick<
	UploadItem,
	'set' | 'name' | 'status' | 'error' | 'document' | 'documentId'
>;

type Stages = Record<StageId, StageState>;

/** Every stage waiting, then the given ones overridden. */
function stages(overrides: Partial<Stages>): Stages {
	return { uploaded: 'waiting', parsed: 'waiting', segmented: 'waiting', ...overrides };
}

/**
 * The status-screen row of one file, from its upload and parse as the upload screen follows them.
 *
 * The backend recognises the text and builds the tree of blocks and clauses in one run, so
 * «Распознан» and «Разбит на блоки» finish together; blocking parse issues fail the latter.
 */
export function progressOf(item: UploadProgress): DocumentProgress {
	const label = `${SET_LABELS[item.set]}: ${item.name}`;
	switch (item.status) {
		case 'uploading':
			return { label, stages: stages({ uploaded: 'running' }), error: null };
		case 'failed':
			return {
				label,
				stages:
					item.documentId === null
						? stages({ uploaded: 'failed' })
						: stages({ uploaded: 'done', parsed: 'failed' }),
				error: item.error
			};
		case 'parsing':
			return { label, stages: stages({ uploaded: 'done', parsed: 'running' }), error: null };
		case 'parsed':
		case 'needs_review': {
			const blocking = item.document?.blocking_issues ?? 0;
			if (blocking > 0) {
				return {
					label,
					stages: stages({ uploaded: 'done', parsed: 'done', segmented: 'failed' }),
					error: `блокирующих проблем разбора: ${blocking}`
				};
			}
			return {
				label,
				stages: stages({ uploaded: 'done', parsed: 'done', segmented: 'done' }),
				error: null
			};
		}
	}
}
