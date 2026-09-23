import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';

import { STAGES, type DocumentProgress, type StageState } from '$lib/status/stages';

import ProcessingStatus from './ProcessingStatus.svelte';

const before = 'До: Положение_2024.docx';
const after = 'После: Положение_2025.pdf';

/** A document whose stages, in column order, are in `states`. */
function row(label: string, states: StageState[], error: string | null = null): DocumentProgress {
	const stages = Object.fromEntries(STAGES.map((stage, index) => [stage.id, states[index]]));
	return { label, stages: stages as DocumentProgress['stages'], error };
}

const allDone = (): DocumentProgress[] => [
	row(before, ['done', 'done', 'done', 'done']),
	row(after, ['done', 'done', 'done', 'done'])
];

const inProgress = (): DocumentProgress[] => [
	row(before, ['done', 'done', 'running', 'waiting']),
	row(after, ['done', 'running', 'waiting', 'waiting'])
];

describe('ProcessingStatus', () => {
	afterEach(() => {
		vi.useRealTimers();
	});

	it('shows every document with the state of each stage', async () => {
		const screen = await render(ProcessingStatus, { rows: inProgress(), ondone: vi.fn() });

		await expect
			.element(screen.getByRole('heading', { name: 'Обработка документов' }))
			.toBeVisible();
		const headers = screen.getByRole('columnheader').elements();
		expect(headers.map((header) => header.textContent?.trim())).toEqual([
			'Документ',
			'Загружен',
			'Распознан',
			'Разбит на блоки',
			'Проанализирован'
		]);
		await expect.element(screen.getByRole('rowheader', { name: before })).toBeVisible();
		const stateTexts = (label: string) =>
			screen
				.getByRole('row', { name: label })
				.getByRole('cell')
				.elements()
				.map((cell) => cell.textContent?.trim());
		expect(stateTexts(before)).toEqual(['готово', 'готово', 'в работе', 'ждёт']);
		expect(stateTexts(after)).toEqual(['готово', 'в работе', 'ждёт', 'ждёт']);
		await expect.element(screen.getByRole('alert')).not.toBeInTheDocument();
		await expect.element(screen.getByText('Готово.')).not.toBeInTheDocument();
	});

	it('says so while there are no documents yet', async () => {
		const screen = await render(ProcessingStatus, { rows: [], ondone: vi.fn() });

		await expect.element(screen.getByText('Ждём список документов…')).toBeVisible();
	});

	it('shows the error of a failed document and never opens the results', async () => {
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
		const ondone = vi.fn<() => void>();
		const rows = [
			row(before, ['done', 'done', 'done', 'done']),
			row(after, ['done', 'failed', 'waiting', 'waiting'], 'Не удалось прочитать PDF')
		];

		const screen = await render(ProcessingStatus, { rows, ondone });

		const alert = screen.getByRole('alert');
		await expect.element(alert).toBeVisible();
		await expect
			.element(alert)
			.toHaveTextContent(`${after} — Этап «Распознан»: Не удалось прочитать PDF`);
		expect(
			screen
				.getByRole('row', { name: after })
				.getByRole('cell')
				.elements()
				.map((cell) => cell.textContent?.trim())
		).toEqual(['готово', 'ошибка', 'ждёт', 'ждёт']);
		vi.advanceTimersByTime(10_000);
		expect(ondone).not.toHaveBeenCalled();
		await expect.element(screen.getByText('Готово.')).not.toBeInTheDocument();
	});

	it('announces completion and calls ondone exactly once, 1200 ms later', async () => {
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
		const ondone = vi.fn<() => void>();

		const screen = await render(ProcessingStatus, { rows: allDone(), ondone });

		await expect
			.element(screen.getByRole('status'))
			.toHaveTextContent('Готово. Открываю «Изменения»…');
		vi.advanceTimersByTime(1199);
		expect(ondone).not.toHaveBeenCalled();
		vi.advanceTimersByTime(1);
		expect(ondone).toHaveBeenCalledOnce();

		await screen.rerender({ rows: allDone() });
		vi.advanceTimersByTime(10_000);
		await screen.rerender({ rows: inProgress() });
		await screen.rerender({ rows: allDone() });
		vi.advanceTimersByTime(10_000);
		expect(ondone).toHaveBeenCalledOnce();
	});

	it('cancels the call when the documents stop being done, and waits in full once they are again', async () => {
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
		const ondone = vi.fn<() => void>();
		const screen = await render(ProcessingStatus, { rows: allDone(), ondone });
		vi.advanceTimersByTime(600);

		await screen.rerender({ rows: inProgress() });
		await expect.element(screen.getByText('Готово.')).not.toBeInTheDocument();
		vi.advanceTimersByTime(10_000);
		expect(ondone).not.toHaveBeenCalled();

		await screen.rerender({ rows: allDone() });
		vi.advanceTimersByTime(1199);
		expect(ondone).not.toHaveBeenCalled();
		vi.advanceTimersByTime(1);
		expect(ondone).toHaveBeenCalledOnce();
	});

	it('cancels the call when the screen goes away', async () => {
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
		const ondone = vi.fn<() => void>();
		const screen = await render(ProcessingStatus, { rows: allDone(), ondone });
		vi.advanceTimersByTime(600);

		await screen.unmount();
		vi.advanceTimersByTime(10_000);

		expect(ondone).not.toHaveBeenCalled();
	});
});
