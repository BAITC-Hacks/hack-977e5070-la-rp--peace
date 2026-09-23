import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
	AnalysisEventHandlers,
	AnalysisOut,
	AnalysisRunApi,
	AnalysisStageOut,
	AnalysisStatus
} from '$lib/api/analyses';
import { ApiError } from '$lib/api/errors';

import {
	ANALYSIS_POLL_INTERVAL_MS,
	AnalysisRun,
	UNAVAILABLE_MESSAGE,
	type AnalysisRequest
} from './analysis-run.svelte';
import { ANALYSIS_STAGE_NAMES } from './analysis-stages';

const ANALYSIS_ID = 12;
const REQUEST: AnalysisRequest = { name: 'Анализ от 23.09.2026', documentIds: [3, 4] };

const stage = (order: number, status: AnalysisStageOut['status']): AnalysisStageOut => ({
	name: ANALYSIS_STAGE_NAMES[order],
	order,
	status
});

/** The run as the backend reports it: every stage `pending` except the ones listed. */
function analysis(
	status: AnalysisStatus,
	stages: Partial<Record<number, AnalysisStageOut['status']>> = {},
	error: string | null = null
): AnalysisOut {
	return {
		id: ANALYSIS_ID,
		name: REQUEST.name,
		status,
		document_ids: [...REQUEST.documentIds],
		error,
		stages: ANALYSIS_STAGE_NAMES.map((_, order) => stage(order, stages[order] ?? 'pending')),
		result: null
	};
}

/** A backend double whose event stream is driven by the test through `stream`. */
function fakeApi(overrides: Partial<AnalysisRunApi> = {}) {
	const stream: { handlers: AnalysisEventHandlers | null; closed: boolean } = {
		handlers: null,
		closed: false
	};
	const api = {
		start: vi.fn(async () => analysis('queued')),
		get: vi.fn(async () => analysis('running')),
		cancel: vi.fn(async () => undefined),
		events: vi.fn((_id: number, handlers: AnalysisEventHandlers) => {
			stream.handlers = handlers;
			stream.closed = false;
			return () => {
				stream.closed = true;
			};
		}),
		...overrides
	} satisfies AnalysisRunApi;
	const emit = (): AnalysisEventHandlers => {
		if (stream.handlers === null) {
			throw new Error('No event stream was opened');
		}
		return stream.handlers;
	};
	return { api, stream, emit };
}

const statuses = (run: AnalysisRun) => run.stages.map((item) => item.status);
const settle = () => vi.advanceTimersByTimeAsync(0);
const nextPoll = () => vi.advanceTimersByTimeAsync(ANALYSIS_POLL_INTERVAL_MS);

beforeEach(() => {
	vi.useFakeTimers();
});

afterEach(() => {
	vi.useRealTimers();
});

describe('AnalysisRun before start', () => {
	it('shows the seven stages of the pipeline, all waiting', () => {
		const run = new AnalysisRun(fakeApi().api);

		expect(run.phase).toBe('idle');
		expect(run.stages.map((item) => item.name)).toEqual([
			'Разбор документов',
			'Подразделения',
			'Сопоставление до/после',
			'Сравнение функций',
			'Потери функций',
			'Дублирование и конфликты',
			'Заключение'
		]);
		expect(new Set(statuses(run))).toEqual(new Set(['pending']));
	});
});

describe('AnalysisRun.start', () => {
	it('starts the run over the documents and follows its event stream', async () => {
		const { api } = fakeApi();
		const run = new AnalysisRun(api);

		await run.start(REQUEST);

		expect(api.start).toHaveBeenCalledWith(REQUEST.name, REQUEST.documentIds);
		expect(api.events).toHaveBeenCalledWith(ANALYSIS_ID, expect.anything());
		expect(run.phase).toBe('running');
		expect(run.analysisId).toBe(ANALYSIS_ID);
		expect(run.isFor([3, 4])).toBe(true);
		expect(run.isFor([3])).toBe(false);
	});

	it('applies stage, log and done events in the order they arrive', async () => {
		const { api, stream, emit } = fakeApi();
		const run = new AnalysisRun(api);
		await run.start(REQUEST);

		emit().stage(stage(0, 'running'));
		emit().log({ at: '2026-09-23T10:00:01Z', message: 'Разбираю «Положение_2024.docx»' });
		emit().stage(stage(0, 'done'));
		emit().stage(stage(1, 'running'));
		emit().log({ at: '2026-09-23T10:00:05Z', message: 'Найдено 14 подразделений' });

		expect(statuses(run).slice(0, 3)).toEqual(['done', 'running', 'pending']);
		expect(run.log.map((entry) => entry.message)).toEqual([
			'Разбираю «Положение_2024.docx»',
			'Найдено 14 подразделений'
		]);

		emit().done();
		expect(run.phase).toBe('done');
		expect(stream.closed).toBe(true);
	});

	it('marks the stage named in an error event failed and keeps the backend message', async () => {
		const { api, stream, emit } = fakeApi();
		const run = new AnalysisRun(api);
		await run.start(REQUEST);

		emit().stage(stage(2, 'running'));
		emit().error({
			message: 'Не удалось сопоставить подразделения',
			stage: stage(2, 'running').name
		});

		expect(run.phase).toBe('failed');
		expect(run.error).toBe('Не удалось сопоставить подразделения');
		expect(statuses(run)[2]).toBe('failed');
		expect(stream.closed).toBe(true);

		emit().stage(stage(3, 'running'));
		expect(statuses(run)[3]).toBe('pending');
	});

	it.each([
		['the endpoint is missing', new ApiError('Сервер пока не поддерживает этот запрос', 404)],
		['the server cannot be reached', new ApiError('Сервер недоступен.', 0)]
	])('says the server does not run analyses yet when %s', async (_, error) => {
		const { api } = fakeApi({ start: vi.fn(async () => Promise.reject(error)) });
		const run = new AnalysisRun(api);

		await run.start(REQUEST);

		expect(run.phase).toBe('unavailable');
		expect(run.error).toBe(UNAVAILABLE_MESSAGE);
		expect(api.events).not.toHaveBeenCalled();
	});

	it('fails with the backend message when the server refuses the run', async () => {
		const refused = new ApiError('Нет документов «После»', 422);
		const run = new AnalysisRun(fakeApi({ start: vi.fn(async () => Promise.reject(refused)) }).api);

		await run.start(REQUEST);

		expect(run.phase).toBe('failed');
		expect(run.error).toBe('Нет документов «После»');
	});

	it('does not subscribe to a run that has already ended', async () => {
		const { api } = fakeApi({ start: vi.fn(async () => analysis('done', { 6: 'done' })) });
		const run = new AnalysisRun(api);

		await run.start(REQUEST);

		expect(run.phase).toBe('done');
		expect(api.events).not.toHaveBeenCalled();
	});
});

describe('AnalysisRun when the stream drops', () => {
	it('polls the run every 2 s until it ends', async () => {
		const get = vi
			.fn<AnalysisRunApi['get']>()
			.mockResolvedValueOnce(analysis('running', { 0: 'done', 1: 'running' }))
			.mockResolvedValueOnce(analysis('done', { 0: 'done', 1: 'done', 6: 'done' }));
		const { api, emit } = fakeApi({ get });
		const run = new AnalysisRun(api);
		await run.start(REQUEST);

		emit().disconnect();
		expect(run.polling).toBe(true);
		await settle();
		expect(get).not.toHaveBeenCalled();

		await nextPoll();
		expect(get).toHaveBeenCalledWith(ANALYSIS_ID);
		expect(statuses(run).slice(0, 2)).toEqual(['done', 'running']);
		expect(run.phase).toBe('running');

		await nextPoll();
		expect(run.phase).toBe('done');
		await nextPoll();
		expect(get).toHaveBeenCalledTimes(2);
	});

	it('keeps polling through a network hiccup, and stops on the run failing', async () => {
		const get = vi
			.fn<AnalysisRunApi['get']>()
			.mockRejectedValueOnce(new ApiError('Сервер недоступен.', 0))
			.mockResolvedValueOnce(analysis('failed', { 4: 'failed' }, 'Модель не ответила'));
		const { api, emit } = fakeApi({ get });
		const run = new AnalysisRun(api);
		await run.start(REQUEST);
		emit().disconnect();

		await nextPoll();
		expect(run.phase).toBe('running');
		await nextPoll();

		expect(run.phase).toBe('failed');
		expect(run.error).toBe('Модель не ответила');
		expect(statuses(run)[4]).toBe('failed');
	});

	it('stops polling on an error that repeating cannot fix', async () => {
		const get = vi
			.fn<AnalysisRunApi['get']>()
			.mockRejectedValue(new ApiError('Анализ не найден', 404));
		const { api, emit } = fakeApi({ get });
		const run = new AnalysisRun(api);
		await run.start(REQUEST);
		emit().disconnect();

		await nextPoll();
		await nextPoll();

		expect(run.phase).toBe('failed');
		expect(run.error).toBe('Анализ не найден');
		expect(get).toHaveBeenCalledOnce();
	});
});

describe('AnalysisRun.cancel', () => {
	it('cancels the run on the server and stops following it', async () => {
		const { api, stream, emit } = fakeApi();
		const run = new AnalysisRun(api);
		await run.start(REQUEST);

		await run.cancel();

		expect(api.cancel).toHaveBeenCalledWith(ANALYSIS_ID);
		expect(run.phase).toBe('cancelled');
		expect(stream.closed).toBe(true);
		emit().done();
		expect(run.phase).toBe('cancelled');
	});

	it('stops polling too once cancelled', async () => {
		const { api, emit } = fakeApi();
		const run = new AnalysisRun(api);
		await run.start(REQUEST);
		emit().disconnect();

		await run.cancel();
		await nextPoll();

		expect(api.get).not.toHaveBeenCalled();
	});

	it('keeps the run going and says why when the server refuses to cancel', async () => {
		const cancel = vi.fn(async () => Promise.reject(new ApiError('Анализ уже завершается', 409)));
		const { api } = fakeApi({ cancel });
		const run = new AnalysisRun(api);
		await run.start(REQUEST);

		await run.cancel();

		expect(run.phase).toBe('running');
		expect(run.cancelError).toBe('Анализ уже завершается');
		expect(run.cancelling).toBe(false);
	});
});

describe('AnalysisRun.retry', () => {
	it('starts a new run over the same documents with a clean log and stages', async () => {
		const start = vi
			.fn<AnalysisRunApi['start']>()
			.mockResolvedValueOnce(analysis('running'))
			.mockResolvedValueOnce({ ...analysis('running'), id: ANALYSIS_ID + 1 });
		const { api, emit } = fakeApi({ start });
		const run = new AnalysisRun(api);
		await run.start(REQUEST);
		emit().log({ at: '2026-09-23T10:00:01Z', message: 'Разбираю документы' });
		emit().error({ message: 'Модель не ответила', stage: stage(0, 'failed').name });

		await run.retry();

		expect(start).toHaveBeenLastCalledWith(REQUEST.name, REQUEST.documentIds);
		expect(run.phase).toBe('running');
		expect(run.analysisId).toBe(ANALYSIS_ID + 1);
		expect(run.error).toBeNull();
		expect(run.log).toEqual([]);
		expect(new Set(statuses(run))).toEqual(new Set(['pending']));
	});

	it('ignores the answer of a start that a newer one has overtaken', async () => {
		let answerFirst: (value: AnalysisOut) => void = () => undefined;
		const start = vi
			.fn<AnalysisRunApi['start']>()
			.mockReturnValueOnce(new Promise((resolve) => (answerFirst = resolve)))
			.mockResolvedValueOnce({ ...analysis('running'), id: ANALYSIS_ID + 1 });
		const run = new AnalysisRun(fakeApi({ start }).api);

		const first = run.start(REQUEST);
		await run.start(REQUEST);
		answerFirst(analysis('done'));
		await first;

		expect(run.analysisId).toBe(ANALYSIS_ID + 1);
		expect(run.phase).toBe('running');
	});
});
