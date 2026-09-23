import { afterEach, describe, expect, it, vi } from 'vitest';
import { userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';

import type { DocumentOut, NodeOut, NodeType } from '$lib/api/document';
import type { CompareSide } from '$lib/diff/view.svelte';

import WordDiff from './WordDiff.svelte';

function node(
	id: number,
	parentId: number | null,
	position: number,
	nodeType: NodeType,
	marker: string,
	text: string
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
		anchor: nodeType === 'section' ? `разд. ${marker}` : `п. ${marker}`,
		path: `п. ${marker}`,
		location: {}
	};
}

function side(id: number, title: string | null, nodes: NodeOut[]): CompareSide {
	const document: DocumentOut = {
		id,
		file_name: `Положение_${id}.docx`,
		set: id === 1 ? 'before' : 'after',
		source_format: 'docx',
		file_size_bytes: 1000,
		content_sha256: 'ab',
		uploaded_at: '2026-09-23T10:00:00Z',
		parse_status: 'parsed',
		title,
		document_type: null,
		organization: null,
		revision: null,
		approved_by: null,
		approval_document_type: null,
		approval_number: null,
		document_created_on: null,
		approved_on: null,
		effective_from: null,
		node_count: nodes.length,
		blocking_issues: 0,
		other_issues: 0
	};
	return { document, nodes };
}

const BEFORE = side(1, 'Положение о ДИБ', [
	node(10, null, 0, 'section', '2', '2. Функции'),
	node(11, 10, 0, 'clause', '2.1', '2.1. Реализует меры по защите информации.'),
	node(12, 10, 1, 'clause', '2.2', '2.2. Отдел режима обеспечивает пропуск.'),
	node(13, 10, 2, 'clause', '2.3', '2.3. Организует мобилизационную подготовку.')
]);

const AFTER = side(2, null, [
	node(20, null, 0, 'section', '2', '2. Функции'),
	node(21, 20, 0, 'clause', '2.1', '2.1. Реализует меры по защите информации.'),
	node(22, 20, 1, 'clause', '2.2', '2.2. Департамент ИБ обеспечивает пропуск.'),
	node(24, 20, 2, 'clause', '2.4', '2.4. Ведёт мониторинг инцидентов.')
]);

function rowOf(container: HTMLElement, nodeId: number): HTMLElement {
	const row = container.querySelector(`#node-${nodeId}`)?.closest<HTMLElement>('[data-row]');
	if (!row) {
		throw new Error(`node ${nodeId} is not rendered`);
	}
	return row;
}

afterEach(() => {
	vi.restoreAllMocks();
});

describe('WordDiff', () => {
	it('names both documents', async () => {
		const screen = await render(WordDiff, { before: BEFORE, after: AFTER });

		await expect.element(screen.getByRole('heading', { name: 'Положение о ДИБ' })).toBeVisible();
		await expect.element(screen.getByText('Положение_1.docx')).toBeVisible();
		await expect.element(screen.getByRole('heading', { name: 'Положение_2.docx' })).toBeVisible();
	});

	it('strikes out deletions and marks insertions inside a changed clause', async () => {
		const screen = await render(WordDiff, { before: BEFORE, after: AFTER });

		const row = rowOf(screen.container, 22);
		expect(row.dataset.status).toBe('changed');
		expect([...row.querySelectorAll('del')].map((el) => el.textContent)).toEqual(['Отдел режима']);
		expect([...row.querySelectorAll('ins')].map((el) => el.textContent)).toEqual([
			'Департамент ИБ'
		]);
		expect(row.querySelector('p')?.textContent).toBe(
			'2.2. Отдел режимаДепартамент ИБ обеспечивает пропуск.'
		);
		expect(getComputedStyle(row.querySelector('del')!).textDecorationLine).toBe('line-through');
		expect(getComputedStyle(row.querySelector('ins')!).textDecorationLine).toBe('underline');
	});

	it('shows removed and added clauses whole, with both sides as anchors', async () => {
		const screen = await render(WordDiff, { before: BEFORE, after: AFTER });

		const removed = rowOf(screen.container, 13);
		expect(removed.dataset.status).toBe('removed');
		expect(removed.querySelector('del')?.textContent).toBe(
			'2.3. Организует мобилизационную подготовку.'
		);
		const added = rowOf(screen.container, 24);
		expect(added.dataset.status).toBe('added');
		expect(added.querySelector('ins')?.textContent).toBe('2.4. Ведёт мониторинг инцидентов.');
		expect(rowOf(screen.container, 12)).toBe(rowOf(screen.container, 22));
		expect(screen.container.querySelector('#node-22')?.textContent).toContain('после: п. 2.2');
	});

	it('hides unchanged clauses until «Только изменения» is turned off', async () => {
		const screen = await render(WordDiff, { before: BEFORE, after: AFTER });

		const toggle = screen.getByRole('checkbox', { name: 'Только изменения' });
		await expect.element(toggle).toBeChecked();
		expect(screen.container.querySelector('#node-21')).toBeNull();
		// The section heading stays as the context of its changed clauses.
		expect(screen.container.querySelector('#node-20')).not.toBeNull();

		await userEvent.click(toggle);

		await expect.element(toggle).not.toBeChecked();
		expect(rowOf(screen.container, 21).dataset.status).toBe('unchanged');
	});

	it('scrolls to and highlights the node named in the hash, even an unchanged one', async () => {
		const scroll = vi.spyOn(HTMLElement.prototype, 'scrollIntoView');
		const screen = await render(WordDiff, { before: BEFORE, after: AFTER, hash: '#node-11' });

		const row = rowOf(screen.container, 11);
		expect(row.getAttribute('aria-current')).toBe('location');
		expect(scroll).toHaveBeenCalledTimes(1);
		expect(scroll.mock.contexts[0]).toBe(row);
		expect(document.activeElement).toBe(row);
		expect(rowOf(screen.container, 22).hasAttribute('aria-current')).toBe(false);
	});

	it('moves the highlight when the hash changes', async () => {
		const scroll = vi.spyOn(HTMLElement.prototype, 'scrollIntoView');
		const screen = await render(WordDiff, { before: BEFORE, after: AFTER, hash: '#node-12' });
		expect(rowOf(screen.container, 22).getAttribute('aria-current')).toBe('location');

		await screen.rerender({ hash: '#node-24' });

		await expect
			.poll(() => rowOf(screen.container, 24).getAttribute('aria-current'))
			.toBe('location');
		expect(rowOf(screen.container, 22).hasAttribute('aria-current')).toBe(false);
		expect(scroll.mock.contexts.at(-1)).toBe(rowOf(screen.container, 24));
	});

	it('says so when the linked node is in neither document', async () => {
		const screen = await render(WordDiff, { before: BEFORE, after: AFTER, hash: '#node-999' });

		await expect
			.element(screen.getByText('Пункт из ссылки не найден в сравниваемых документах.'))
			.toBeVisible();
	});

	it('says so when the documents have no differences', async () => {
		const screen = await render(WordDiff, { before: BEFORE, after: side(3, null, BEFORE.nodes) });

		await expect
			.element(screen.getByText('Изменений нет: тексты пунктов совпадают.'))
			.toBeVisible();
	});
});
