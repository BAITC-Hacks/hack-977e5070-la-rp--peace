// Analyses as planned in .agents/backend.md (slice 2, «Analyses and live progress»), which the
// backend does not serve yet — a proposed contract, to be confirmed with the backend owner.
// `result` follows docs/spec/tz_site.md §5.3 (result.json), the format the results screen draws.

import type { JobResult } from '$lib/result/types';

import { API_URL, request } from './client';

/** Lifecycle of an analysis run. */
export type AnalysisStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

/** State of one pipeline stage (tz_site.md §6.2: ожидает / идёт / готово / ошибка). */
export type AnalysisStageStatus = 'pending' | 'running' | 'done' | 'failed';

/** One stage of the pipeline, e.g. «Извлечение подразделений». */
export interface AnalysisStageOut {
	/** Shown to the user as is. */
	name: string;
	order: number;
	status: AnalysisStageStatus;
}

/** `GET /api/analyses/{id}`: the run, its stages and, once `done`, its result. */
export interface AnalysisOut {
	id: number;
	name: string;
	status: AnalysisStatus;
	document_ids: number[];
	/** Why the run failed, as the backend reports it; null while nothing went wrong. */
	error: string | null;
	stages: AnalysisStageOut[];
	result: JobResult | null;
}

/** Analysis operations; injected so the pages' logic is testable. */
export interface AnalysesApi {
	/** `POST /api/analyses`: starts a run over the given documents. */
	start(name: string, documentIds: readonly number[]): Promise<AnalysisOut>;
	get(id: number): Promise<AnalysisOut>;
}

async function start(name: string, documentIds: readonly number[]): Promise<AnalysisOut> {
	const response = await request('/api/analyses', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ name, document_ids: documentIds })
	});
	return (await response.json()) as AnalysisOut;
}

async function get(id: number): Promise<AnalysisOut> {
	const response = await request(`/api/analyses/${id}`);
	return (await response.json()) as AnalysisOut;
}

export const analysesApi: AnalysesApi = { start, get };

// The status screen follows a run live: `GET /api/analyses/{id}/events` (SSE: `stage`, `log`,
// `done`, `error`) and `POST /api/analyses/{id}/cancel`, per .agents/frontend.md §2.2 and §4.

/** A `log` event: one step of the agent, e.g. «Найдено 14 подразделений в „Оргструктура.xlsx“». */
export interface AgentLogEntry {
	/** ISO timestamp of the step. */
	at: string;
	message: string;
}

/** An `error` event: the run has stopped. */
export interface AnalysisFailure {
	message: string;
	/** `name` of the stage that failed, when the backend knows it. */
	stage: string | null;
}

/** What `events` reports; after `done`, `error` or `disconnect` nothing more arrives. */
export interface AnalysisEventHandlers {
	stage(stage: AnalysisStageOut): void;
	log(entry: AgentLogEntry): void;
	done(): void;
	error(failure: AnalysisFailure): void;
	/** The stream dropped before the run ended; the caller has to poll `get` instead. */
	disconnect(): void;
}

/** Everything the status screen does with a run. */
export interface AnalysisRunApi extends AnalysesApi {
	cancel(id: number): Promise<void>;
	/** Subscribes to the run's events; returns the function that unsubscribes. */
	events(id: number, handlers: AnalysisEventHandlers): () => void;
}

async function cancel(id: number): Promise<void> {
	await request(`/api/analyses/${id}/cancel`, { method: 'POST' });
}

/** The JSON payload of an SSE message; a malformed one is a backend bug and is logged. */
function payload<T>(event: MessageEvent): T | null {
	try {
		return JSON.parse(String(event.data)) as T;
	} catch (error) {
		console.error('Malformed analysis event', event.type, event.data, error);
		return null;
	}
}

function events(id: number, handlers: AnalysisEventHandlers): () => void {
	const source = new EventSource(`${API_URL}/api/analyses/${id}/events`);
	let open = true;
	const close = () => {
		open = false;
		source.close();
	};
	const on = <T>(type: string, handle: (data: T) => void) =>
		source.addEventListener(type, (event) => {
			const data = open && event instanceof MessageEvent ? payload<T>(event) : null;
			if (data !== null) {
				handle(data);
			}
		});

	on<AnalysisStageOut>('stage', (stage) => handlers.stage(stage));
	on<AgentLogEntry>('log', (entry) => handlers.log(entry));
	// `done` carries nothing the screen needs, so its data is not parsed.
	source.addEventListener('done', () => {
		if (open) {
			close();
			handlers.done();
		}
	});
	// A server-sent `error` event is a MessageEvent with data; a dropped connection is a bare
	// Event of the same name. EventSource would reconnect on its own, but §2.2 wants polling.
	source.addEventListener('error', (event) => {
		if (!open) {
			return;
		}
		close();
		if (event instanceof MessageEvent) {
			handlers.error(
				payload<AnalysisFailure>(event) ?? { message: 'Анализ завершился с ошибкой.', stage: null }
			);
		} else {
			handlers.disconnect();
		}
	});
	return close;
}

export const analysisRunApi: AnalysisRunApi = { ...analysesApi, cancel, events };
