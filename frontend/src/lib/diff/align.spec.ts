import { describe, expect, it } from 'vitest';

import type { NodeOut, NodeType } from '$lib/api/document';

import {
	MAX_COMPARED_PAIRS,
	SIMILARITY_THRESHOLD,
	alignDocuments,
	textSimilarity,
	type DiffBlock
} from './align';

function node(
	id: number,
	parentId: number | null,
	position: number,
	nodeType: NodeType,
	marker: string | null,
	text: string,
	path = marker ? `п. ${marker}` : `абз. ${position + 1}`
): NodeOut {
	return {
		id,
		parent_id: parentId,
		position,
		node_type: nodeType,
		marker,
		text,
		source_start: 0,
		source_end: text.length,
		anchor: path,
		path,
		location: {}
	};
}

/** `status before→after` per row, heads included, for compact expectations. */
function summary(blocks: readonly DiffBlock[]): string[][] {
	const line = (row: DiffBlock['rows'][number]) =>
		`${row.status} ${row.before?.id ?? '-'}→${row.after?.id ?? '-'}`;
	return blocks.map((block) => [
		block.head === null ? 'loose' : line(block.head),
		...block.rows.map(line)
	]);
}

describe('textSimilarity', () => {
	it('ignores case, punctuation and the node number', () => {
		const a = node(1, null, 0, 'clause', '2.1', '2.1. Отдел режима обеспечивает пропуск.');
		const b = node(2, null, 0, 'clause', '2.3', '2.3. отдел режима обеспечивает пропуск');
		expect(textSimilarity(a, b)).toBe(1);
	});

	it('is low for different functions of the same unit', () => {
		const a = node(1, null, 0, 'clause', '2.1', '2.1. ДИБ реализует меры по защите информации.');
		const b = node(2, null, 0, 'clause', '2.2', '2.2. ДИБ ведёт мониторинг инцидентов.');
		expect(textSimilarity(a, b)).toBeLessThan(SIMILARITY_THRESHOLD);
	});
});

describe('alignDocuments', () => {
	it('pairs clauses by marker inside the paired section and tells kept from changed', () => {
		const before = [
			node(1, null, 0, 'section', '1', '1. Структура', 'Разд. 1 «Структура»'),
			node(2, 1, 0, 'clause', '1.1', '1.1. В структуру входит Отдел кадров.'),
			node(3, 1, 1, 'clause', '1.2', '1.2. Управление IT подчиняется Председателю.')
		];
		const after = [
			node(11, null, 0, 'section', '1', '1. Структура', 'Разд. 1 «Структура»'),
			node(
				12,
				11,
				0,
				'clause',
				'1.1',
				'1.1. В структуру входит Департамент по работе с персоналом.'
			),
			node(13, 11, 1, 'clause', '1.2', '1.2. Управление IT подчиняется Председателю.')
		];

		expect(summary(alignDocuments(before, after))).toEqual([
			['unchanged 1→11', 'changed 2→12', 'unchanged 3→13']
		]);
	});

	it('keeps a rewritten clause under its number as one changed clause', () => {
		const before = [
			node(1, null, 0, 'section', '2', '2. Функции'),
			node(2, 1, 0, 'clause', '2.1', '2.1. Обеспечивает мобилизационную подготовку.')
		];
		const after = [
			node(11, null, 0, 'section', '2', '2. Функции'),
			node(12, 11, 0, 'clause', '2.1', '2.1. Ведёт мониторинг инцидентов безопасности.')
		];

		expect(summary(alignDocuments(before, after))).toEqual([['unchanged 1→11', 'changed 2→12']]);
	});

	it('places a removed clause where it was and an added one where it is', () => {
		const before = [
			node(1, null, 0, 'section', '2', '2. Функции'),
			node(2, 1, 0, 'clause', '2.1', '2.1. Реализует меры по защите информации.'),
			node(3, 1, 1, 'clause', '2.2', '2.2. Обеспечивает мобилизационную подготовку.'),
			node(4, 1, 2, 'clause', '2.3', '2.3. Проводит закупки товаров.')
		];
		const after = [
			node(11, null, 0, 'section', '2', '2. Функции'),
			node(12, 11, 0, 'clause', '2.1', '2.1. Реализует меры по защите информации.'),
			node(13, 11, 1, 'clause', '2.2', '2.2. Проводит закупки товаров.'),
			node(14, 11, 2, 'clause', '2.3', '2.3. Ведёт мониторинг инцидентов безопасности.')
		];

		expect(summary(alignDocuments(before, after))).toEqual([
			['unchanged 1→11', 'unchanged 2→12', 'removed 3→-', 'changed 4→13', 'added -→14']
		]);
	});

	it('recognises renumbered clauses by their text instead of pairing them by number', () => {
		const before = [
			node(1, null, 0, 'section', '2', '2. Функции'),
			node(2, 1, 0, 'clause', '2.1', '2.1. Реализует меры по защите информации.'),
			node(3, 1, 1, 'clause', '2.2', '2.2. Обеспечивает пропускной режим.')
		];
		const after = [
			node(11, null, 0, 'section', '2', '2. Функции'),
			node(12, 11, 0, 'clause', '2.1', '2.1. Ведёт мониторинг инцидентов.'),
			node(13, 11, 1, 'clause', '2.2', '2.2. Реализует меры по защите информации.'),
			node(14, 11, 2, 'clause', '2.3', '2.3. Обеспечивает пропускной и внутриобъектовый режим.')
		];

		expect(summary(alignDocuments(before, after))).toEqual([
			['unchanged 1→11', 'added -→12', 'changed 2→13', 'changed 3→14']
		]);
	});

	it('pairs clauses without a common marker by similar text above the threshold', () => {
		const before = [
			node(1, null, 0, 'text', null, 'Отдел режима обеспечивает пропускной режим.', 'абз. 1'),
			node(2, null, 1, 'text', null, 'Совершенно другой абзац про закупки.', 'абз. 2')
		];
		const after = [
			node(11, null, 0, 'text', null, 'Вводный абзац новой редакции.', 'абз. 1'),
			node(12, null, 1, 'text', null, 'Департамент ИБ обеспечивает пропускной режим.', 'абз. 2'),
			node(13, null, 2, 'text', null, 'Ещё один новый абзац.', 'абз. 3')
		];

		expect(summary(alignDocuments(before, after))).toEqual([
			['loose', 'added -→11', 'changed 1→12', 'removed 2→-', 'added -→13']
		]);
	});

	it('takes the subtree of a removed or added node along', () => {
		const before = [
			node(1, null, 0, 'section', '3', '3. Отдел режима'),
			node(2, 1, 0, 'clause', '3.1', '3.1. Обеспечивает пропуск.'),
			node(3, 2, 0, 'list_item', 'а', 'а) ведёт журнал;', 'п. 3.1 «а»')
		];
		const after = [
			node(11, null, 0, 'section', '4', '4. Центр цифровой трансформации'),
			node(12, 11, 0, 'clause', '4.1', '4.1. Разрабатывает стратегию.')
		];

		const blocks = alignDocuments(before, after);

		expect(summary(blocks)).toEqual([
			['removed 1→-', 'removed 2→-', 'removed 3→-'],
			['added -→11', 'added -→12']
		]);
		expect(blocks[0].rows.map((row) => row.depth)).toEqual([1, 2]);
	});

	it('shows a clause moved to another section as removed plus added', () => {
		const before = [
			node(1, null, 0, 'section', '1', '1. Служба аудита'),
			node(2, 1, 0, 'clause', '1.1', '1.1. Проводит аудит информационной безопасности.'),
			node(3, null, 1, 'section', '2', '2. Департамент ИБ')
		];
		const after = [
			node(11, null, 0, 'section', '1', '1. Служба аудита'),
			node(13, null, 1, 'section', '2', '2. Департамент ИБ'),
			node(14, 13, 0, 'clause', '2.1', '2.1. Проводит аудит информационной безопасности.')
		];

		expect(summary(alignDocuments(before, after))).toEqual([
			['unchanged 1→11', 'removed 2→-'],
			['unchanged 3→13', 'added -→14']
		]);
	});

	it('groups consecutive loose top-level text into one block without a head', () => {
		const before = [
			node(1, null, 0, 'service', null, 'УТВЕРЖДЕНО Советом директоров', 'Вводная часть › абз. 1'),
			node(2, null, 1, 'section', '1', '1. Общие положения'),
			node(3, 2, 0, 'clause', '1.1', '1.1. Положение определяет задачи.')
		];
		const after = [
			node(11, null, 0, 'service', null, 'УТВЕРЖДЕНО Советом директоров', 'Вводная часть › абз. 1'),
			node(12, null, 1, 'service', null, 'Редакция 2', 'Вводная часть › абз. 2'),
			node(13, null, 2, 'section', '1', '1. Общие положения'),
			node(14, 13, 0, 'clause', '1.1', '1.1. Положение определяет задачи.')
		];

		expect(summary(alignDocuments(before, after))).toEqual([
			['loose', 'unchanged 1→11', 'added -→12'],
			['unchanged 2→13', 'unchanged 3→14']
		]);
	});

	it('ignores whitespace-only differences', () => {
		const before = [node(1, null, 0, 'clause', '1', '1.  Текст\nпункта ')];
		const after = [node(11, null, 0, 'clause', '1', '1. Текст пункта')];

		expect(summary(alignDocuments(before, after))).toEqual([['loose', 'unchanged 1→11']]);
	});

	it('still pairs identical texts in documents too large to compare pair by pair', () => {
		const count = Math.ceil(Math.sqrt(MAX_COMPARED_PAIRS)) + 1;
		const texts = Array.from({ length: count }, (_, i) => `Абзац номер ${i} о функции ${i}.`);
		const before = texts.map((text, i) => node(i + 1, null, i, 'text', null, text, 'абз.'));
		const after = [...texts]
			.reverse()
			.map((text, i) => node(10_000 + i, null, i, 'text', null, text, 'абз.'));

		const [block] = alignDocuments(before, after);

		expect(block.rows).toHaveLength(count);
		expect(block.rows.every((row) => row.status === 'unchanged')).toBe(true);
	});

	it('returns no blocks for two empty documents', () => {
		expect(alignDocuments([], [])).toEqual([]);
	});
});
