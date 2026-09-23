import { describe, expect, it } from 'vitest';

import type { AnalysisStageOut } from '$lib/api/analyses';

import {
	defaultAnalysisName,
	initialStages,
	logTime,
	mergeStages,
	stageState
} from './analysis-stages';

const stage = (name: string, order: number, status: AnalysisStageOut['status']) => ({
	name,
	order,
	status
});

describe('mergeStages', () => {
	it('updates a stage by name and keeps the others', () => {
		const merged = mergeStages(initialStages(), [stage('Подразделения', 1, 'running')]);

		expect(merged).toHaveLength(7);
		expect(merged.map((item) => item.status).slice(0, 3)).toEqual([
			'pending',
			'running',
			'pending'
		]);
	});

	it('adds a stage it does not know, in pipeline order', () => {
		const merged = mergeStages(
			[stage('Разбор', 1, 'done'), stage('Заключение', 3, 'pending')],
			[stage('Проверка цитат', 2, 'running')]
		);

		expect(merged.map((item) => item.name)).toEqual(['Разбор', 'Проверка цитат', 'Заключение']);
	});
});

describe('stageState', () => {
	it('names a pending stage «waiting» and keeps the other states', () => {
		expect(stageState('pending')).toBe('waiting');
		expect(stageState('failed')).toBe('failed');
	});
});

describe('defaultAnalysisName', () => {
	it('names the run after the date', () => {
		expect(defaultAnalysisName(new Date(2026, 8, 23))).toBe('Анализ от 23.09.2026');
	});
});

describe('logTime', () => {
	it('shows the time of a step, or the raw value when it is not a timestamp', () => {
		expect(logTime('2026-09-23T10:00:05')).toBe('10:00:05');
		expect(logTime('вчера')).toBe('вчера');
	});
});
