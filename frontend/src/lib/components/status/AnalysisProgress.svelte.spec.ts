import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';

import type { AnalysisEventHandlers, AnalysisOut, AnalysisRunApi } from '$lib/api/analyses';
import { ApiError } from '$lib/api/errors';
import { AnalysisRun } from '$lib/status/analysis-run.svelte';
import { ANALYSIS_STAGE_NAMES } from '$lib/status/analysis-stages';

import AnalysisProgress from './AnalysisProgress.svelte';

const running: AnalysisOut = {
	id: 5,
	name: 'Анализ от 23.09.2026',
	status: 'running',
	document_ids: [1, 2],
	error: null,
	stages: ANALYSIS_STAGE_NAMES.map((name, order) => ({
		name,
		order,
		status: order === 0 ? 'running' : 'pending'
	})),
	result: null
};

/** A run started against a backend double; `emit` drives its event stream. */
async function startedRun(overrides: Partial<AnalysisRunApi> = {}) {
	let handlers: AnalysisEventHandlers | null = null;
	const api: AnalysisRunApi = {
		start: vi.fn(async () => running),
		get: vi.fn(async () => running),
		cancel: vi.fn(async () => undefined),
		events: vi.fn((_id: number, next: AnalysisEventHandlers) => {
			handlers = next;
			return () => undefined;
		}),
		...overrides
	};
	const run = new AnalysisRun(api);
	await run.start({ name: running.name, documentIds: running.document_ids });
	const emit = () => {
		if (handlers === null) {
			throw new Error('No event stream was opened');
		}
		return handlers;
	};
	return { api, run, emit };
}

const props = (run: AnalysisRun, onopen = vi.fn<() => void>()) => ({
	run,
	onopen,
	doneText: 'Открываю изменения…',
	unavailableText: 'Открываю демонстрационный результат…'
});

describe('AnalysisProgress', () => {
	afterEach(() => {
		vi.useRealTimers();
	});

	it('shows every stage with its state and the agent log', async () => {
		const { run, emit } = await startedRun();
		const screen = await render(AnalysisProgress, props(run));

		emit().log({ at: '2026-09-23T10:00:01Z', message: 'Найдено 14 подразделений' });

		const stages = screen.getByRole('listitem').elements().slice(0, 7);
		expect(stages.map((item) => item.textContent?.replace(/\s+/g, ' ').trim())).toEqual(
			ANALYSIS_STAGE_NAMES.map((name, order) => `${name} ${order === 0 ? 'в работе' : 'ждёт'}`)
		);
		await expect.element(screen.getByText('Найдено 14 подразделений')).toBeVisible();
	});

	it('cancels the run', async () => {
		const { api, run } = await startedRun();
		const screen = await render(AnalysisProgress, props(run));

		await screen.getByRole('button', { name: 'Отменить' }).click();

		expect(api.cancel).toHaveBeenCalledWith(running.id);
		await expect.element(screen.getByText('Анализ отменён.')).toBeVisible();
	});

	it('shows the error of a failed run and starts it again on «Повторить»', async () => {
		const { api, run, emit } = await startedRun();
		const screen = await render(AnalysisProgress, props(run));

		emit().error({ message: 'Модель не ответила', stage: ANALYSIS_STAGE_NAMES[0] });

		await expect.element(screen.getByRole('alert')).toHaveTextContent('Модель не ответила');
		await screen.getByRole('button', { name: 'Повторить' }).click();
		expect(api.start).toHaveBeenCalledTimes(2);
		await expect.element(screen.getByRole('button', { name: 'Отменить' })).toBeVisible();
	});

	it('says the server does not run analyses yet, then opens the next page', async () => {
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
		const onopen = vi.fn<() => void>();
		const { run } = await startedRun({
			start: vi.fn(async () => Promise.reject(new ApiError('Not Found', 404)))
		});
		const screen = await render(AnalysisProgress, props(run, onopen));

		await expect
			.element(screen.getByRole('status'))
			.toHaveTextContent(
				'Анализ пока не запускается на сервере. Открываю демонстрационный результат…'
			);
		vi.advanceTimersByTime(1200);
		expect(onopen).toHaveBeenCalledOnce();
	});

	it('opens the result 1200 ms after the run is done', async () => {
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
		const onopen = vi.fn<() => void>();
		const { run, emit } = await startedRun();
		const screen = await render(AnalysisProgress, props(run, onopen));

		emit().done();

		await expect
			.element(screen.getByRole('status'))
			.toHaveTextContent('Готово. Открываю изменения…');
		vi.advanceTimersByTime(1199);
		expect(onopen).not.toHaveBeenCalled();
		vi.advanceTimersByTime(1);
		expect(onopen).toHaveBeenCalledOnce();
	});
});
