import type {
	AgentLogEntry,
	AnalysisFailure,
	AnalysisOut,
	AnalysisRunApi,
	AnalysisStageOut
} from '$lib/api/analyses';
import { ApiError, describeError } from '$lib/api/errors';

import { initialStages, mergeStages } from './analysis-stages';

/** How often the run is re-read once its event stream has dropped (.agents/frontend.md §2.2). */
export const ANALYSIS_POLL_INTERVAL_MS = 2000;

export const UNAVAILABLE_MESSAGE = 'Анализ пока не запускается на сервере';

/**
 * `unavailable`: the backend has no analysis endpoint yet or cannot be reached, so the run never
 * started. `failed`: it started, or was refused, with an error to show.
 */
export type RunPhase =
	'idle' | 'starting' | 'running' | 'done' | 'failed' | 'cancelled' | 'unavailable';

/** What a run is started with: `POST /api/analyses` `{name, document_ids}`. */
export interface AnalysisRequest {
	name: string;
	documentIds: readonly number[];
}

/** Whether a failed `create` means the server does not run analyses, rather than refusing this one. */
function isUnavailable(error: unknown): boolean {
	return error instanceof ApiError && (error.status === 0 || error.status === 404);
}

/**
 * One analysis run, followed from `POST /api/analyses` to its end: stages and the agent log come
 * from the event stream, or from polling `GET /api/analyses/{id}` once the stream drops.
 */
export class AnalysisRun {
	phase = $state<RunPhase>('idle');
	analysisId = $state<number | null>(null);
	/** In pipeline order; the defaults of §2.2 until the backend reports its own. */
	stages = $state.raw<AnalysisStageOut[]>(initialStages());
	log = $state.raw<AgentLogEntry[]>([]);
	/** Why the run failed or could not start; null otherwise. */
	error = $state<string | null>(null);
	/** The event stream dropped: the stages are re-read every ANALYSIS_POLL_INTERVAL_MS. */
	polling = $state(false);
	cancelling = $state(false);
	/** Why «Отменить» did not work; the run goes on. */
	cancelError = $state<string | null>(null);

	readonly #api: AnalysisRunApi;
	#request: AnalysisRequest | null = null;
	#unsubscribe: (() => void) | null = null;
	#timer: ReturnType<typeof setTimeout> | null = null;
	/** Bumped by every start and by dispose, so answers for an older run are dropped. */
	#generation = 0;

	constructor(api: AnalysisRunApi) {
		this.#api = api;
	}

	/** Whether this run was started for exactly these documents. */
	isFor(documentIds: readonly number[]): boolean {
		const ids = this.#request?.documentIds;
		return (
			ids !== undefined &&
			ids.length === documentIds.length &&
			ids.every((id, index) => id === documentIds[index])
		);
	}

	/** Starts a new run, dropping whatever the previous one was doing. */
	async start(request: AnalysisRequest): Promise<void> {
		const generation = this.#reset();
		this.#request = request;
		this.phase = 'starting';
		let analysis: AnalysisOut;
		try {
			analysis = await this.#api.start(request.name, request.documentIds);
		} catch (error) {
			if (generation === this.#generation) {
				this.phase = isUnavailable(error) ? 'unavailable' : 'failed';
				this.error = isUnavailable(error) ? UNAVAILABLE_MESSAGE : describeError(error);
			}
			return;
		}
		if (generation !== this.#generation) {
			return;
		}
		this.analysisId = analysis.id;
		if (this.#apply(analysis)) {
			this.#subscribe(analysis.id, generation);
		}
	}

	/** «Повторить»: a new run over the same documents. */
	async retry(): Promise<void> {
		if (this.#request !== null) {
			await this.start(this.#request);
		}
	}

	/** «Отменить». */
	async cancel(): Promise<void> {
		const id = this.analysisId;
		if (id === null || this.phase !== 'running' || this.cancelling) {
			return;
		}
		const generation = this.#generation;
		this.cancelling = true;
		this.cancelError = null;
		try {
			await this.#api.cancel(id);
			if (generation === this.#generation && this.phase === 'running') {
				this.#stopFollowing();
				this.phase = 'cancelled';
			}
		} catch (error) {
			if (generation === this.#generation) {
				this.cancelError = describeError(error);
			}
		} finally {
			if (generation === this.#generation) {
				this.cancelling = false;
			}
		}
	}

	/** Stops following the run; answers still in flight are ignored. */
	dispose(): void {
		this.#generation += 1;
		this.#stopFollowing();
	}

	#reset(): number {
		this.dispose();
		this.phase = 'idle';
		this.analysisId = null;
		this.stages = initialStages();
		this.log = [];
		this.error = null;
		this.polling = false;
		this.cancelling = false;
		this.cancelError = null;
		return this.#generation;
	}

	#stopFollowing(): void {
		this.#unsubscribe?.();
		this.#unsubscribe = null;
		if (this.#timer !== null) {
			clearTimeout(this.#timer);
			this.#timer = null;
		}
	}

	#subscribe(id: number, generation: number): void {
		const live = () => generation === this.#generation && this.phase === 'running';
		this.#unsubscribe = this.#api.events(id, {
			stage: (stage) => live() && (this.stages = mergeStages(this.stages, [stage])),
			log: (entry) => live() && this.#addLog(entry),
			done: () => live() && this.#finish(),
			error: (failure) => live() && this.#fail(failure),
			disconnect: () => {
				if (live()) {
					this.#unsubscribe = null;
					this.polling = true;
					this.#schedulePoll(id, generation);
				}
			}
		});
	}

	#schedulePoll(id: number, generation: number): void {
		this.#timer = setTimeout(() => {
			this.#timer = null;
			void this.#poll(id, generation);
		}, ANALYSIS_POLL_INTERVAL_MS);
	}

	async #poll(id: number, generation: number): Promise<void> {
		try {
			const analysis = await this.#api.get(id);
			if (generation === this.#generation && this.phase === 'running') {
				this.#apply(analysis);
			}
		} catch (error) {
			if (generation !== this.#generation || this.phase !== 'running') {
				return;
			}
			if (!(error instanceof ApiError && error.retriable)) {
				this.#fail({ message: describeError(error), stage: null });
				return;
			}
		}
		if (generation === this.#generation && this.phase === 'running') {
			this.#schedulePoll(id, generation);
		}
	}

	/**
	 * Takes over the stages and the outcome of the run as `GET` or `POST` returned it; true while
	 * the run goes on.
	 */
	#apply(analysis: AnalysisOut): boolean {
		// The backend's full list replaces the defaults of §2.2 rather than mixing with them.
		if (analysis.stages.length > 0) {
			this.stages = mergeStages([], analysis.stages);
		}
		switch (analysis.status) {
			case 'queued':
			case 'running':
				this.phase = 'running';
				return true;
			case 'done':
				this.#finish();
				return false;
			case 'cancelled':
				this.#stopFollowing();
				this.phase = 'cancelled';
				return false;
			case 'failed':
				this.#fail({ message: analysis.error ?? 'Анализ завершился с ошибкой.', stage: null });
				return false;
		}
	}

	#addLog(entry: AgentLogEntry): void {
		this.log = [...this.log, entry];
	}

	#finish(): void {
		this.#stopFollowing();
		this.phase = 'done';
	}

	#fail(failure: AnalysisFailure): void {
		this.#stopFollowing();
		const failed = failure.stage;
		if (failed !== null) {
			this.stages = this.stages.map((stage) =>
				stage.name === failed ? { ...stage, status: 'failed' } : stage
			);
		}
		this.error = failure.message;
		this.phase = 'failed';
	}
}
