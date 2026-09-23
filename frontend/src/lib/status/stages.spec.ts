import { describe, expect, it } from 'vitest';

import {
	STAGES,
	documentErrors,
	errorMessage,
	failedStage,
	overallStatus,
	type DocumentProgress,
	type StageId,
	type StageState
} from './stages';

/** A document with every stage in `state`, then the listed stages overridden. */
function row(
	label: string,
	state: StageState,
	overrides: Partial<Record<StageId, StageState>> = {},
	error: string | null = null
): DocumentProgress {
	const stages = Object.fromEntries(STAGES.map((stage) => [stage.id, state])) as Record<
		StageId,
		StageState
	>;
	return { label, stages: { ...stages, ...overrides }, error };
}

const before = 'До: Положение_2024.docx';
const after = 'После: Положение_2025.pdf';

describe('STAGES', () => {
	it('lists the columns of the status table in pipeline order', () => {
		expect(STAGES.map((stage) => stage.label)).toEqual([
			'Загружен',
			'Распознан',
			'Разбит на блоки',
			'Проанализирован'
		]);
	});
});

describe('failedStage', () => {
	it('finds the first failed stage', () => {
		const failed = row(before, 'done', { segmented: 'failed', analyzed: 'failed' });

		expect(failedStage(failed)?.label).toBe('Разбит на блоки');
	});

	it('is null while no stage has failed', () => {
		expect(failedStage(row(before, 'done', { analyzed: 'running' }))).toBeNull();
	});
});

describe('errorMessage', () => {
	it('names the failed stage before the backend message', () => {
		const failed = row(before, 'done', { parsed: 'failed' }, 'Файл повреждён');

		expect(errorMessage(failed)).toBe('Этап «Распознан»: Файл повреждён');
	});

	it('shows the backend message alone when no stage is marked failed', () => {
		expect(errorMessage(row(before, 'waiting', {}, 'Сервер недоступен'))).toBe('Сервер недоступен');
	});

	it('reports a failed stage that came without a message', () => {
		expect(errorMessage(row(before, 'done', { analyzed: 'failed' }, '  '))).toBe(
			'Этап «Проанализирован» завершился с ошибкой.'
		);
	});

	it('is null while the document is fine', () => {
		expect(errorMessage(row(before, 'running'))).toBeNull();
	});
});

describe('documentErrors', () => {
	it('keeps only the failed documents, in table order', () => {
		const rows = [
			row(before, 'done', { parsed: 'failed' }, 'Файл повреждён'),
			row(after, 'done'),
			row('НПА: 2 файла', 'waiting', {}, 'Сервер недоступен')
		];

		expect(documentErrors(rows)).toEqual([
			{ label: before, message: 'Этап «Распознан»: Файл повреждён' },
			{ label: 'НПА: 2 файла', message: 'Сервер недоступен' }
		]);
	});
});

describe('overallStatus', () => {
	it('is done only when every stage of every document is done', () => {
		expect(overallStatus([row(before, 'done'), row(after, 'done')])).toBe('done');
		expect(overallStatus([row(before, 'done'), row(after, 'done', { analyzed: 'running' })])).toBe(
			'running'
		);
		expect(overallStatus([row(before, 'done'), row(after, 'done', { analyzed: 'waiting' })])).toBe(
			'running'
		);
	});

	it('is failed when any stage of any document has failed, even while others still run', () => {
		const rows = [row(before, 'running'), row(after, 'done', { segmented: 'failed' })];

		expect(overallStatus(rows)).toBe('failed');
	});

	it('is failed when a document carries an error message', () => {
		expect(overallStatus([row(before, 'done', {}, 'Сервер недоступен')])).toBe('failed');
	});

	it('is running while there are no documents yet', () => {
		expect(overallStatus([])).toBe('running');
	});
});
