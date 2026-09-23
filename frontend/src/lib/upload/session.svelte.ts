import type { DocumentsApi } from '$lib/api/client';
import { ApiError, describeError } from '$lib/api/errors';
import type { DocSet, DocumentOut, ParseStatus } from '$lib/api/types';

import { isAccepted } from './files';

/** How often a document is re-read while the backend parses it. */
export const POLL_INTERVAL_MS = 2000;

/**
 * `parsing`: the backend has stored the file and parses it in the background.
 * `parsed` and `needs_review`: parsing has ended with that outcome.
 */
export type UploadStatus = 'uploading' | 'parsing' | 'parsed' | 'needs_review' | 'failed';

const STATUS_OF: Record<ParseStatus, UploadStatus> = {
	pending: 'parsing',
	parsed: 'parsed',
	validated: 'parsed',
	needs_review: 'needs_review'
};

const STATUS_LABELS: Record<Exclude<UploadStatus, 'uploading'>, string> = {
	parsing: 'Разбирается…',
	parsed: 'Разобран',
	needs_review: 'Требует проверки',
	failed: 'Ошибка'
};

/** One file dropped into an upload zone, from the first byte sent until it is removed. */
export class UploadItem {
	readonly key = crypto.randomUUID();
	readonly file: File;
	readonly set: DocSet;
	status = $state<UploadStatus>('uploading');
	/** Share of bytes sent, 0..1. */
	progress = $state(0);
	/** The stored document, re-read while the backend parses it. */
	document = $state.raw<DocumentOut | null>(null);
	error = $state<string | null>(null);
	/** Whether the failed step can succeed if repeated (network or server error). */
	retriable = $state(false);
	/** A type change or deletion is in flight. */
	busy = $state(false);

	constructor(file: File, set: DocSet) {
		this.file = file;
		this.set = set;
	}

	/** Parsing has ended, so the document's structure and type can be looked at. */
	get parsed(): boolean {
		return this.status === 'parsed' || this.status === 'needs_review';
	}

	/** Until the backend answers the upload there is no document to delete yet. */
	get removable(): boolean {
		return this.status !== 'uploading' && !this.busy;
	}

	get statusLabel(): string {
		if (this.status === 'uploading') {
			return `Загрузка ${Math.round(this.progress * 100)}%`;
		}
		return STATUS_LABELS[this.status];
	}
}

function delay(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Files of the new-analysis screen across all document sets, kept in sync with the backend. */
export class UploadSession {
	items = $state<UploadItem[]>([]);
	readonly #api: DocumentsApi;
	#disposed = false;

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

	/** Repeats the failed step: sends the file again, or resumes following a stored document. */
	retry(item: UploadItem): void {
		if (item.status !== 'failed') {
			return;
		}
		const { document } = item;
		void (document === null ? this.#upload(item) : this.#follow(item, document));
	}

	/** Changes the document type at once and reverts it if the backend refuses. */
	async setType(item: UploadItem, documentType: string): Promise<void> {
		const previous = item.document;
		const value = documentType.trim();
		if (previous === null || !item.parsed || item.busy) {
			return;
		}
		if (value === '' || value === previous.document_type) {
			return;
		}
		item.busy = true;
		item.error = null;
		item.document = { ...previous, document_type: value };
		try {
			item.document = await this.#api.setType(previous.id, value);
		} catch (error) {
			item.document = previous;
			item.error = describeError(error);
		} finally {
			item.busy = false;
		}
	}

	/** Deletes the stored document, if any, then drops the file, which also ends its polling. */
	async remove(item: UploadItem): Promise<void> {
		if (!item.removable) {
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
					item.error = describeError(error);
					item.busy = false;
					return;
				}
			}
		}
		this.items = this.items.filter((other) => other !== item);
	}

	/** Stops polling for every file, e.g. when the page is left. */
	dispose(): void {
		this.#disposed = true;
	}

	/** Whether the file is still on screen, so its polling should go on. */
	#tracks(item: UploadItem): boolean {
		return !this.#disposed && this.items.includes(item);
	}

	#fail(item: UploadItem, error: unknown): void {
		item.status = 'failed';
		item.error = describeError(error);
		item.retriable = error instanceof ApiError && error.retriable;
	}

	async #upload(item: UploadItem): Promise<void> {
		item.status = 'uploading';
		item.progress = 0;
		item.error = null;
		item.retriable = false;
		let document: DocumentOut;
		try {
			document = await this.#api.upload(item.file, item.set, (fraction) => {
				item.progress = fraction;
			});
		} catch (error) {
			this.#fail(item, error);
			return;
		}
		item.document = document;
		await this.#follow(item, document);
	}

	/** Re-reads the document every `POLL_INTERVAL_MS` while it is `pending`. */
	async #follow(item: UploadItem, stored: DocumentOut): Promise<void> {
		item.error = null;
		item.retriable = false;
		let document = stored;
		while (document.parse_status === 'pending') {
			item.status = 'parsing';
			await delay(POLL_INTERVAL_MS);
			if (!this.#tracks(item)) {
				return;
			}
			try {
				document = await this.#api.get(document.id);
			} catch (error) {
				if (this.#tracks(item)) {
					this.#fail(item, error);
				}
				return;
			}
			if (!this.#tracks(item)) {
				return;
			}
			item.document = document;
		}
		item.status = STATUS_OF[document.parse_status];
	}
}
