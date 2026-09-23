import { describe, expect, it } from 'vitest';

import fixture from '$lib/fixtures/result.json';
import { visibleFindings } from '$lib/result/derive';
import type { Finding, FindingType, JobResult } from '$lib/result/types';

import { ANALYSIS_TABS, tabAfterKey, tabFindings } from './tabs';

// JSON imports type enum values as plain strings; src/lib/fixtures/result.spec.ts checks them.
const result = fixture as JobResult;

function finding(id: string, type: FindingType): Finding {
	return {
		id,
		type,
		block: 'ИБ и режим',
		title: id,
		from: [],
		to: [],
		evidence: { conclusion: 'Вывод', method: 'Метод', steps: [], confidence: 'medium' },
		review: null
	};
}

function tab(id: string) {
	const found = ANALYSIS_TABS.find((candidate) => candidate.id === id);
	if (found === undefined) {
		throw new Error(`no tab ${id}`);
	}
	return found;
}

describe('ANALYSIS_TABS', () => {
	it('lists the four sub-pages of tech task §6.5 in order', () => {
		expect(ANALYSIS_TABS.map((candidate) => candidate.label)).toEqual([
			'Потеря функций',
			'Дублирование',
			'Конфликт интересов',
			'Пересечение зон'
		]);
	});

	it('puts contradictions next to conflicts of interest', () => {
		expect(tab('conflict').types).toEqual(['conflict', 'contradiction']);
	});

	it('gives every tab its own empty message', () => {
		expect(tab('duplication').empty).toBe('Дублирований не найдено');
		expect(new Set(ANALYSIS_TABS.map((candidate) => candidate.empty)).size).toBe(4);
	});
});

describe('tabFindings', () => {
	it('keeps the tab types in result order and drops every other type', () => {
		const findings = [
			finding('C-1', 'conflict'),
			finding('C-2', 'kept'),
			finding('C-3', 'contradiction'),
			finding('C-4', 'overlap'),
			finding('C-5', 'conflict')
		];

		expect(tabFindings(findings, tab('conflict')).map((item) => item.id)).toEqual([
			'C-1',
			'C-3',
			'C-5'
		]);
		expect(tabFindings(findings, tab('overlap')).map((item) => item.id)).toEqual(['C-4']);
		expect(tabFindings(findings, tab('loss'))).toEqual([]);
	});

	it('sorts every problem finding of the demo fixture into exactly one tab (P1.1)', () => {
		const shown = visibleFindings(result);
		const sorted = ANALYSIS_TABS.flatMap((candidate) => tabFindings(shown, candidate));
		const problems = shown.filter((item) => ANALYSIS_TABS.some((t) => t.types.includes(item.type)));

		expect(sorted.map((item) => item.id).sort()).toEqual(problems.map((item) => item.id).sort());
		expect(tabFindings(shown, tab('loss')).map((item) => item.id)).toEqual(['C-011']);
		expect(tabFindings(shown, tab('duplication')).map((item) => item.id)).toEqual(['C-013']);
		expect(tabFindings(shown, tab('conflict')).map((item) => item.id)).toEqual(['C-010']);
		expect(tabFindings(shown, tab('overlap')).map((item) => item.id)).toEqual(['C-014']);
	});
});

describe('tabAfterKey', () => {
	it('moves along the arrows and wraps around at both ends', () => {
		expect(tabAfterKey('ArrowRight', 0, 4)).toBe(1);
		expect(tabAfterKey('ArrowRight', 3, 4)).toBe(0);
		expect(tabAfterKey('ArrowLeft', 2, 4)).toBe(1);
		expect(tabAfterKey('ArrowLeft', 0, 4)).toBe(3);
	});

	it('jumps to the first and last tab with Home and End', () => {
		expect(tabAfterKey('Home', 2, 4)).toBe(0);
		expect(tabAfterKey('End', 1, 4)).toBe(3);
	});

	it('ignores other keys', () => {
		expect(tabAfterKey('Enter', 1, 4)).toBeNull();
		expect(tabAfterKey('ArrowDown', 1, 4)).toBeNull();
	});
});
