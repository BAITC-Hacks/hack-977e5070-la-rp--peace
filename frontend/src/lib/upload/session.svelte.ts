import type { DocumentsApi } from '$lib/api/client';
import { ApiError } from '$lib/api/errors';
import type { ApiDocument, DocSet, DocType } from '$lib/api/types';

import { isAccepted } from './files';

/** `processing`: all bytes sent, the backend is parsing the document. */
export type UploadStatus = 'uploading' | 'processing' | 'done' | 'failed';

/** One file dropped into an upload zone, from the first byte sent until it is removed. */
export class UploadItem {
	readonly key = crypto.randomUUID();
	readonly file: File;
	readonly set: DocSet;
	status = $state<UploadStatus>('uploading');
	/** Share of bytes sent, 0..1. */
	progress = $state(0);
	/** The stored document once the backend has accepted and parsed the file. */
	document = $state.raw<ApiDocument | null>(null);
	error = $state<string | null>(null);
	/** Whether the failed upload can succeed if sent again (network or server error). */
	retriable = $state(false);
	/** A type change or deletion is in flight. */
	busy = $state(false);

	constructor(file: File, set: DocSet) {
		this.file = file;
		this.set = set;
	}

	get inFlight(): boolean {
		return this.status === 'uploading' || this.status === 'processing';
	}
}

function messageOf(error: unknown): string {
	if (error instanceof ApiError) {
		return error.message;
	}
	console.error(error);
	return error instanceof Error ? error.message : String(error);
}

/** Files of the new-analysis screen across all document sets, kept in sync with the backend. */
export class UploadSession {
	items = $state<UploadItem[]>([]);
	readonly #api: DocumentsApi;

	constructor(api: DocumentsApi) {
		this.#api = api;
	}

	itemsIn(set: DocSet): UploadItem[] {
		return this.items.filter((item) => item.set === set);
	}

	/** Starts uploading every accepted file and returns the names of the rejected ones. */
	add(set: DocSet, files: Iterable<File>): string[] {
		const rejected: string[] = [];
		for (const file of files) {
			if (!isAccepted(file.name)) {
				rejected.push(file.name);
				continue;
			}
			const item = new UploadItem(file, set);
			this.items.push(item);
			void this.#upload(item);
		}
		return rejected;
	}

	retry(item: UploadItem): void {
		if (item.status === 'failed') {
			void this.#upload(item);
		}
	}

	/** Changes the document type at once and reverts it if the backend refuses. */
	async setType(item: UploadItem, docType: DocType): Promise<void> {
		const previous = item.document;
		if (previous === null || item.busy || previous.doc_type === docType) {
			return;
		}
		item.busy = true;
		item.error = null;
		item.document = { ...previous, doc_type: docType };
		try {
			item.document = await this.#api.setType(previous.id, docType);
		} catch (error) {
			item.document = previous;
			item.error = messageOf(error);
		} finally {
			item.busy = false;
		}
	}

	/** Deletes the stored document, if any, then drops the file from its zone. */
	async remove(item: UploadItem): Promise<void> {
		if (item.inFlight || item.busy) {
			return;
		}
		if (item.document !== null) {
			item.busy = true;
			item.error = null;
			try {
				await this.#api.remove(item.document.id);
			} catch (error) {
				const alreadyGone = error instanceof ApiError && error.status === 404;
				if (!alreadyGone) {
					item.error = messageOf(error);
					item.busy = false;
					return;
				}
			}
		}
		this.items = this.items.filter((other) => other !== item);
	}

	async #upload(item: UploadItem): Promise<void> {
		item.status = 'uploading';
		item.progress = 0;
		item.error = null;
		item.retriable = false;
		try {
			item.document = await this.#api.upload(item.file, item.set, (fraction) => {
				item.progress = fraction;
				if (fraction >= 1) {
					item.status = 'processing';
				}
			});
			item.status = 'done';
		} catch (error) {
			item.status = 'failed';
			item.error = messageOf(error);
			item.retriable = error instanceof ApiError && error.retriable;
		}
	}
}
