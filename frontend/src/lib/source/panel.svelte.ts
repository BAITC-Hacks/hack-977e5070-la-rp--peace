import { ApiError } from '$lib/api/errors';
import type { SourceRef, SourcesApi } from '$lib/api/sources';
import { compareHref } from '$lib/diff/anchor';

/** One citation of a finding: a document node and the exact words cited from it. */
export interface SourceTarget {
	nodeId: number;
	/** Cited words; without them the node's whole text is the source. */
	quote?: string;
}

/**
 * `not_found`: the backend could not find the cited words in the node (HTTP 422), so the
 * finding that relies on them is not confirmed by the documents (tz_site.md §2, I2).
 */
export type SourceStatus = 'loading' | 'ready' | 'not_found' | 'failed';

export const QUOTE_NOT_FOUND_MESSAGE = 'Цитата не найдена в документе — вывод не подтверждён';

/** Answer of `POST /api/sources/resolve` when the quote does not occur in the cited text. */
const QUOTE_NOT_FOUND_STATUS = 422;

function messageOf(error: unknown): string {
	if (error instanceof ApiError) {
		return error.message;
	}
	console.error(error);
	return error instanceof Error ? error.message : String(error);
}

/** The «До» and «После» documents the Word view compares. */
export interface ComparePair {
	before: number;
	after: number;
}

/** The source panel: the citations of one finding, browsed one at a time. */
export class SourcePanelState {
	/** Citations being browsed; empty while the panel is closed. */
	targets = $state.raw<SourceTarget[]>([]);
	index = $state(0);
	status = $state<SourceStatus>('loading');
	source = $state.raw<SourceRef | null>(null);
	error = $state<string | null>(null);
	/** Whether the failed lookup can succeed if repeated (network or server error). */
	retriable = $state(false);
	readonly #api: SourcesApi;
	readonly #compare: () => ComparePair | null;
	/** Bumped by every lookup and by `close`, so an answer that arrives too late is dropped. */
	#request = 0;

	/** `compare` gives the documents of the Word view; without them the panel does not link to it. */
	constructor(api: SourcesApi, compare: () => ComparePair | null = () => null) {
		this.#api = api;
		this.#compare = compare;
	}

	get isOpen(): boolean {
		return this.targets.length > 0;
	}

	get current(): SourceTarget | null {
		return this.targets[this.index] ?? null;
	}

	get hasPrev(): boolean {
		return this.index > 0;
	}

	get hasNext(): boolean {
		return this.index < this.targets.length - 1;
	}

	/** Download link of the original file of the shown source. */
	get downloadUrl(): string | null {
		return this.source && this.#api.fileUrl(this.source.document_id);
	}

	/** Link to the shown source in the Word view, when it belongs to one of the compared documents. */
	get compareHref(): ReturnType<typeof compareHref> | null {
		const compare = this.#compare();
		const { source } = this;
		if (compare === null || source === null) {
			return null;
		}
		const inPair = source.document_id === compare.before || source.document_id === compare.after;
		return inPair ? compareHref(compare.before, compare.after, source.node_id) : null;
	}

	/** Shows the citation at `index` of `targets`; an empty list leaves the panel as it is. */
	open(targets: readonly SourceTarget[], index = 0): Promise<void> {
		if (targets.length === 0) {
			return Promise.resolve();
		}
		this.targets = [...targets];
		return this.#show(Math.min(Math.max(index, 0), targets.length - 1));
	}

	prev(): Promise<void> {
		return this.hasPrev ? this.#show(this.index - 1) : Promise.resolve();
	}

	next(): Promise<void> {
		return this.hasNext ? this.#show(this.index + 1) : Promise.resolve();
	}

	retry(): Promise<void> {
		return this.status === 'failed' ? this.#show(this.index) : Promise.resolve();
	}

	close(): void {
		this.#request += 1;
		this.targets = [];
		this.index = 0;
		this.#reset();
	}

	#reset(): void {
		this.status = 'loading';
		this.source = null;
		this.error = null;
		this.retriable = false;
	}

	async #show(index: number): Promise<void> {
		const request = ++this.#request;
		const { nodeId, quote } = this.targets[index];
		this.index = index;
		this.#reset();
		try {
			const source =
				quote === undefined
					? await this.#api.getNodeSource(nodeId)
					: await this.#api.resolveSource(nodeId, quote);
			if (request === this.#request) {
				this.source = source;
				this.status = 'ready';
			}
		} catch (error) {
			if (request !== this.#request) {
				return;
			}
			if (error instanceof ApiError && error.status === QUOTE_NOT_FOUND_STATUS) {
				this.status = 'not_found';
				return;
			}
			this.status = 'failed';
			this.error = messageOf(error);
			this.retriable = error instanceof ApiError && error.retriable;
		}
	}
}
