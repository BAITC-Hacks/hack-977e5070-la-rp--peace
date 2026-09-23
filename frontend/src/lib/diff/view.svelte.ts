import type { DocumentApi, DocumentOut, NodeOut } from '$lib/api/document';
import { describeError } from '$lib/api/errors';
import { POLL_INTERVAL_MS } from '$lib/document/view.svelte';

/**
 * - `missing`: the address does not name two documents;
 * - `same`: both sides are the same document;
 * - `pending`: a document is still being parsed, checked again every `POLL_INTERVAL_MS`;
 * - `ready`: both cards and node lists are loaded, with no blocking parsing issues;
 * - `failed`: a request failed or parsing has blocking issues.
 */
export type CompareStatus = 'missing' | 'same' | 'loading' | 'pending' | 'ready' | 'failed';

export type Side = 'before' | 'after';

/** One document of the comparison. */
export interface CompareSide {
	document: DocumentOut;
	nodes: NodeOut[];
}

const SIDE_LABELS: Record<Side, string> = { before: '«До»', after: '«После»' };

/** Rejections keep the side, so the message can say which document failed. */
class SideError extends Error {
	readonly side: Side;
	readonly reason: unknown;

	constructor(side: Side, reason: unknown) {
		super(`${side} document failed`);
		this.side = side;
		this.reason = reason;
	}
}

async function forSide<T>(side: Side, request: Promise<T>): Promise<T> {
	try {
		return await request;
	} catch (error) {
		throw new SideError(side, error);
	}
}

/** The «Изменения → Word» page: the cards and nodes of both documents. */
export class CompareView {
	readonly beforeId: number | null;
	readonly afterId: number | null;
	status = $state<CompareStatus>('loading');
	before = $state.raw<CompareSide | null>(null);
	after = $state.raw<CompareSide | null>(null);
	error = $state<string | null>(null);
	readonly #api: DocumentApi;
	#timer: ReturnType<typeof setTimeout> | undefined;
	#stopped = false;

	constructor(api: DocumentApi, beforeId: number | null, afterId: number | null) {
		this.#api = api;
		this.beforeId = beforeId;
		this.afterId = afterId;
		if (beforeId === null || afterId === null) {
			this.status = 'missing';
		} else if (beforeId === afterId) {
			this.status = 'same';
		}
	}

	/** Starts loading; state changes only when the backend answers, never synchronously. */
	start(): void {
		if (this.status === 'loading') {
			void this.#load();
		}
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
		const { beforeId, afterId } = this;
		if (beforeId === null || afterId === null) {
			return;
		}
		try {
			const [before, after] = await Promise.all([
				forSide('before', this.#api.get(beforeId)),
				forSide('after', this.#api.get(afterId))
			]);
			if (this.#stopped) {
				return;
			}
			if (before.parse_status === 'pending' || after.parse_status === 'pending') {
				this.status = 'pending';
				this.#timer = setTimeout(() => void this.#load(), POLL_INTERVAL_MS);
				return;
			}
			const blocked = (
				[
					['before', before],
					['after', after]
				] as const
			)
				.filter(([, document]) => document.blocking_issues > 0)
				.map(([side]) => SIDE_LABELS[side]);
			if (blocked.length > 0) {
				this.status = 'failed';
				this.error = `Сравнение недоступно: в ${blocked.length > 1 ? 'документах' : 'документе'} ${blocked.join(' и ')} есть блокирующие проблемы разбора. Откройте документ, чтобы посмотреть ошибки.`;
				return;
			}
			this.status = 'loading';
			const [beforeNodes, afterNodes] = await Promise.all([
				forSide('before', this.#api.nodes(beforeId)),
				forSide('after', this.#api.nodes(afterId))
			]);
			if (this.#stopped) {
				return;
			}
			this.before = { document: before, nodes: beforeNodes };
			this.after = { document: after, nodes: afterNodes };
			this.status = 'ready';
		} catch (error) {
			if (this.#stopped) {
				return;
			}
			this.status = 'failed';
			this.error =
				error instanceof SideError
					? `Документ ${SIDE_LABELS[error.side]}: ${describeError(error.reason)}`
					: describeError(error);
		}
	}
}
