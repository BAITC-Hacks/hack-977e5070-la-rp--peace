import { describe, expect, it } from 'vitest';

import {
	blockFindings,
	countByType,
	findingSources,
	findingsOfItem,
	focusOf,
	isSourced,
	linkedItems,
	splitConclusion,
	visibleFindings
} from './derive';
import type { Block, Finding, JobResult, Source } from './types';

function source(item: string, quote = 'проводит аудит системы защиты информации'): Source {
	return {
		doc: 'after',
		block: 'Положение ДИБиР',
		node_id: 42,
		clause: 'п. 2.8',
		quote,
		item
	};
}

function finding(id: string, overrides: Partial<Finding> = {}): Finding {
	return {
		id,
		type: 'moved',
		block: 'ИБ и режим',
		title: 'Перенесено',
		desc: null,
		from: [],
		to: [],
		evidence: {
			conclusion: 'Вывод',
			method: 'Метод',
			steps: [{ kind: 'fact', text: 'Факт', sources: [source('g_audit')] }],
			confidence: 'high'
		},
		review: null,
		...overrides
	};
}

function unsourced(id: string, quote?: string): Finding {
	const sources = quote === undefined ? [] : [source('g_x', quote)];
	return finding(id, {
		evidence: {
			conclusion: 'Вывод без цитат',
			method: 'Метод',
			steps: [
				{ kind: 'fact', text: 'Факт', sources },
				{ kind: 'inference', text: 'Рассуждение', sources: [] }
			],
			confidence: 'low'
		}
	});
}

function result(findings: Finding[], overrides: Partial<JobResult> = {}): JobResult {
	return {
		job_id: 'job-1',
		summary: { changed_blocks: [], counts: {} },
		conclusion: '',
		blocks: [],
		findings: Object.fromEntries(findings.map((item) => [item.id, item])),
		...overrides
	};
}

describe('findingSources', () => {
	it('collects the sources of every step in order', () => {
		const first = source('f_audit');
		const second = source('g_audit');
		const item = finding('C-010', {
			evidence: {
				conclusion: 'Вывод',
				method: 'Метод',
				steps: [
					{ kind: 'fact', text: 'До', sources: [first] },
					{ kind: 'inference', text: 'Рассуждение', sources: [] },
					{ kind: 'fact', text: 'После', sources: [second] }
				],
				confidence: 'high'
			}
		});

		expect(findingSources(item)).toEqual([first, second]);
	});
});

describe('isSourced (I1)', () => {
	it('accepts a finding with a quoted source', () => {
		expect(isSourced(finding('C-001'))).toBe(true);
	});

	it('rejects a finding without sources', () => {
		expect(isSourced(unsourced('C-002'))).toBe(false);
	});

	it('rejects a finding whose only quote is blank', () => {
		expect(isSourced(unsourced('C-003', '  '))).toBe(false);
	});
});

describe('visibleFindings', () => {
	it('drops findings without sources', () => {
		const shown = finding('C-001');

		expect(visibleFindings(result([shown, unsourced('C-002')]))).toEqual([shown]);
	});
});

describe('blockFindings', () => {
	it('keeps the block order and skips unknown and unsourced ids', () => {
		const first = finding('C-001');
		const third = finding('C-003');
		const block: Block = {
			title: 'Структура',
			before: [],
			after: [],
			changes: ['C-003', 'C-404', 'C-002', 'C-001']
		};
		const findings = result([first, unsourced('C-002'), third]).findings;

		expect(blockFindings(block, findings)).toEqual([third, first]);
	});
});

describe('countByType', () => {
	it('counts per type in the order of the type list, leaving out absent types', () => {
		const counts = countByType([
			finding('C-1', { type: 'loss' }),
			finding('C-2', { type: 'kept' }),
			finding('C-3', { type: 'kept' }),
			finding('C-4', { type: 'overlap' })
		]);

		expect(counts).toEqual([
			{ type: 'kept', count: 2 },
			{ type: 'loss', count: 1 },
			{ type: 'overlap', count: 1 }
		]);
	});

	it('returns nothing for no findings', () => {
		expect(countByType([])).toEqual([]);
	});
});

describe('linked items and focus', () => {
	const conflict = finding('C-010', {
		type: 'conflict',
		from: ['f_audit'],
		to: ['g_audit'],
		also: ['g_prot']
	});
	const kept = finding('C-007', { type: 'kept', from: ['f_prot'], to: ['g_prot'] });
	const loss = finding('C-011', { type: 'loss', from: ['f_mob'], to: [] });
	const row = [kept, conflict, loss];

	it('lists from, to and also', () => {
		expect(linkedItems(conflict)).toEqual(['f_audit', 'g_audit', 'g_prot']);
		expect(linkedItems(loss)).toEqual(['f_mob']);
	});

	it('finds every finding that touches an item', () => {
		expect(findingsOfItem(row, 'g_prot')).toEqual(['C-007', 'C-010']);
		expect(findingsOfItem(row, 'nothing')).toEqual([]);
	});

	it('lights the focused findings and all their items', () => {
		const focus = focusOf(row, ['C-007', 'C-010']);

		expect([...focus.findings]).toEqual(['C-007', 'C-010']);
		expect([...focus.items].sort()).toEqual(['f_audit', 'f_prot', 'g_audit', 'g_prot']);
	});

	it('lights nothing without focus', () => {
		const focus = focusOf(row, []);

		expect(focus.findings.size).toBe(0);
		expect(focus.items.size).toBe(0);
	});
});

describe('splitConclusion', () => {
	it('turns mentions of shown findings into references', () => {
		const parts = splitConclusion(
			'Мобподготовка не закреплена (C-011); ИТ-стратегия дублируется (C-013).',
			new Set(['C-011', 'C-013'])
		);

		expect(parts).toEqual([
			{ kind: 'text', text: 'Мобподготовка не закреплена (' },
			{ kind: 'finding', id: 'C-011' },
			{ kind: 'text', text: '); ИТ-стратегия дублируется (' },
			{ kind: 'finding', id: 'C-013' },
			{ kind: 'text', text: ').' }
		]);
	});

	it('leaves mentions of hidden findings as text', () => {
		expect(splitConclusion('См. C-404 и C-001', new Set(['C-001']))).toEqual([
			{ kind: 'text', text: 'См. C-404 и ' },
			{ kind: 'finding', id: 'C-001' }
		]);
	});

	it('keeps a text without mentions whole', () => {
		expect(splitConclusion('Изменений нет.', new Set())).toEqual([
			{ kind: 'text', text: 'Изменений нет.' }
		]);
	});

	it('returns nothing for an empty text', () => {
		expect(splitConclusion('', new Set(['C-001']))).toEqual([]);
	});
});
