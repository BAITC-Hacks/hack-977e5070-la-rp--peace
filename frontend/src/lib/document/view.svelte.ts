import type { DocumentApi, DocumentOut, IssueOut, NodeOut, ProfileOut } from '$lib/api/document';
import { ApiError } from '$lib/api/errors';

/** How often a document still being parsed is checked again. */
export const POLL_INTERVAL_MS = 2000;

/**
 * - `loading`: requests in flight (`document` is set once the card has arrived);
 * - `pending`: the backend is still parsing, checked again every `POLL_INTERVAL_MS`;
 * - `ready`: `document` and `details` are loaded.
 */
export type ViewStatus = 'loading' | 'pending' | 'ready' | 'not_found' | 'failed';

/** Everything the page shows below the header once parsing has finished. */
export interface DocumentDetails {
	nodes: NodeOut[];
	issues: IssueOut[];
	profile: ProfileOut;
}

/** Document id from the route, or null for anything that cannot be one. */
export function parseDocumentId(param: string): number | null {
	return /^[1-9]\d{0,15}$/.test(param) ? Number(param) : null;
}

function messageOf(error: unknown): string {
	if (error instanceof ApiError) {
		return error.message;
	}
	console.error(error);
	return error instanceof Error ? error.message : String(error);
}

/** The document page: card, issues and tree, loaded once parsing is over. */
export class DocumentView {
	readonly id: number | null;
	status = $state<ViewStatus>('loading');
	document = $state.raw<DocumentOut | null>(null);
	details = $state.raw<DocumentDetails | null>(null);
	error = $state<string | null>(null);
	readonly #api: DocumentApi;
	#timer: ReturnType<typeof setTimeout> | undefined;
	#stopped = false;

	constructor(api: DocumentApi, id: number | null) {
		this.#api = api;
		this.id = id;
		if (id === null) {
			this.status = 'not_found';
		}
	}

	/** Starts loading; state changes only when the backend answers, never synchronously. */
	start(): void {
		void this.#load();
	}

	/** Stops polling and ignores answers still in flight; call when the page goes away. */
	stop(): void {
		this.#stopped = true;
		clearTimeout(this.#timer);
	}

	retry(): void {
		if (this.status === 'failed') {
			this.status = 'loading';
			this.error = null;
			void this.#load();
		}
	}

	async #load(): Promise<void> {
		const id = this.id;
		if (id === null) {
			return;
		}
		try {
			const document = await this.#api.get(id);
			if (this.#stopped) {
				return;
			}
			this.document = document;
			if (document.parse_status === 'pending') {
				this.status = 'pending';
				this.#timer = setTimeout(() => void this.#load(), POLL_INTERVAL_MS);
				return;
			}
			this.status = 'loading';
			const [nodes, issues, profile] = await Promise.all([
				this.#api.nodes(id),
				this.#api.issues(id),
				this.#api.profile(id)
			]);
			if (this.#stopped) {
				return;
			}
			this.details = { nodes, issues, profile };
			this.status = 'ready';
		} catch (error) {
			if (this.#stopped) {
				return;
			}
			if (error instanceof ApiError && error.status === 404) {
				this.status = 'not_found';
			} else {
				this.status = 'failed';
				this.error = messageOf(error);
			}
		}
	}
}
