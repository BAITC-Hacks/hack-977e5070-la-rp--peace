import { describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';

import '../../../routes/layout.css';

import type { NodeOut, NodeType } from '$lib/api/document';
import { TreeState } from '$lib/document/tree-state.svelte';

import NodeTree from './NodeTree.svelte';

function node(
	id: number,
	parentId: number | null,
	position: number,
	nodeType: NodeType,
	marker: string | null,
	anchor: string,
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
		anchor,
		path: anchor,
		location: {}
	};
}

const LONG_TEXT =
	'3.5. Руководитель службы внутреннего аудита ежегодно представляет Совету директоров отчёт ' +
	'о результатах деятельности, включая сведения о выполнении плана проверок, существенных рисках, ' +
	'вопросах корпоративного управления и контроля, а также иную информацию по запросу Совета ' +
	'директоров и Комитета по аудиту, в сроки, установленные планом работы. Хвост_текста_пункта.';

const NODES = [
	node(1, null, 0, 'service', null, 'вводная часть', 'УТВЕРЖДЕНО Советом директоров'),
	node(10, null, 1, 'section', '3', 'разд. 3', '3. Структура и организация работы'),
	node(11, 10, 0, 'clause', '3.4', 'п. 3.4', '3.4. Служба внутреннего аудита:'),
	node(12, 11, 0, 'list_item', 'а', 'п. 3.4 «а»', 'а) проводит аудит системы защиты информации;'),
	node(13, 10, 1, 'clause', '3.5', 'п. 3.5', LONG_TEXT),
	node(20, null, 2, 'table', null, 'вводная часть, таблица 1', 'Лист согласования')
];

function item(container: HTMLElement, id: number): HTMLElement {
	const element = container.querySelector<HTMLElement>(`[data-node-id="${id}"]`);
	if (element === null) {
		throw new Error(`node ${id} is not rendered`);
	}
	return element;
}

const LONG_WORD =
	'Положение_о_департаменте_информационной_безопасности_и_рисков_редакция_2025_года';

/** A 360 px phone screen: the page column is a grid, so it grows with unbreakable content. */
async function phoneFrame(): Promise<HTMLElement> {
	await page.viewport(360, 800);
	const frame = document.createElement('div');
	frame.style.cssText = 'display: grid; width: 360px; padding-inline: 16px; box-sizing: border-box';
	document.body.append(frame);
	return frame;
}

describe('NodeTree', () => {
	it('shows top-level nodes with their children and folds deeper levels', async () => {
		const screen = await render(NodeTree, { tree: new TreeState(NODES) });

		await expect.element(screen.getByRole('tree')).toBeVisible();
		await expect.element(screen.getByText('3. Структура и организация работы')).toBeVisible();
		await expect.element(screen.getByText('3.4. Служба внутреннего аудита:')).toBeVisible();
		await expect.element(screen.getByText('а) проводит аудит')).not.toBeInTheDocument();
		expect(item(screen.container, 10).getAttribute('aria-expanded')).toBe('true');
		expect(item(screen.container, 11).getAttribute('aria-expanded')).toBe('false');
		expect(item(screen.container, 11).getAttribute('aria-level')).toBe('2');
		expect(item(screen.container, 20).hasAttribute('aria-expanded')).toBe(false);
	});

	it('shows the marker, the anchor and the kind of each node', async () => {
		const screen = await render(NodeTree, { tree: new TreeState(NODES) });

		const clause = item(screen.container, 11);
		expect(clause.textContent).toContain('3.4');
		expect(clause.textContent).toContain('п. 3.4');
		expect(clause.textContent).toContain('пункт');
		expect(item(screen.container, 10).textContent).toContain('раздел');
		expect(item(screen.container, 20).textContent).toContain('таблица');
		expect(item(screen.container, 1).textContent).toContain('служебный');
		expect(item(screen.container, 1).firstElementChild?.classList).toContain('text-muted');
	});

	it('expands a node on click of its toggle', async () => {
		const screen = await render(NodeTree, { tree: new TreeState(NODES) });

		await screen.getByRole('button', { name: 'Развернуть', exact: true }).click();

		await expect.element(screen.getByText('а) проводит аудит')).toBeVisible();
		expect(item(screen.container, 11).getAttribute('aria-expanded')).toBe('true');
	});

	it('folds long text until asked to show all of it', async () => {
		const screen = await render(NodeTree, { tree: new TreeState(NODES) });
		await expect.element(screen.getByText('Хвост_текста_пункта')).not.toBeInTheDocument();

		await screen.getByRole('button', { name: 'показать полностью' }).click();

		await expect.element(screen.getByText('Хвост_текста_пункта')).toBeVisible();
		await screen.getByRole('button', { name: 'свернуть текст' }).click();
		await expect.element(screen.getByText('Хвост_текста_пункта')).not.toBeInTheDocument();
	});

	it('works from the keyboard', async () => {
		const screen = await render(NodeTree, { tree: new TreeState(NODES) });
		const service = item(screen.container, 1);
		expect(service.tabIndex).toBe(0);
		expect(item(screen.container, 10).tabIndex).toBe(-1);
		service.focus();

		await userEvent.keyboard('{ArrowDown}{ArrowDown}');
		const clause = item(screen.container, 11);
		await expect.element(clause).toHaveFocus();
		expect(clause.getAttribute('aria-selected')).toBe('true');
		expect(clause.tabIndex).toBe(0);

		await userEvent.keyboard('{ArrowRight}');
		await expect.element(screen.getByText('а) проводит аудит')).toBeVisible();
		await userEvent.keyboard('{ArrowRight}');
		await expect.element(item(screen.container, 12)).toHaveFocus();

		await userEvent.keyboard('{ArrowLeft}{ArrowLeft}');
		await expect.element(clause).toHaveFocus();
		await expect.element(screen.getByText('а) проводит аудит')).not.toBeInTheDocument();
	});

	it('offers the source of a node only when a handler is given', async () => {
		const onopen = vi.fn();
		const screen = await render(NodeTree, { tree: new TreeState(NODES), onopen });

		const buttons = screen.getByRole('button', { name: 'Источник' });
		expect(buttons.elements()).toHaveLength(5);
		await buttons.nth(2).click();

		expect(onopen).toHaveBeenCalledWith(11);
	});

	it('has no source buttons without a handler', async () => {
		const screen = await render(NodeTree, { tree: new TreeState(NODES) });

		await expect.element(screen.getByRole('button', { name: 'Источник' })).not.toBeInTheDocument();
	});

	it('says so when the document has no structure', async () => {
		const screen = await render(NodeTree, { tree: new TreeState([]) });

		await expect.element(screen.getByText('Структура документа не извлечена.')).toBeVisible();
	});

	it('wraps long markers, places and texts within a phone screen', async () => {
		const frame = await phoneFrame();
		const deep = [0, 1, 2, 3, 4, 5].map((level) =>
			node(
				200 + level,
				level === 0 ? null : 199 + level,
				0,
				'clause',
				`2.${'8.'.repeat(level)}1`,
				`after:dibr:2.${'8.'.repeat(level)}1`,
				`Департамент обеспечивает ${LONG_WORD}`
			)
		);
		const tree = new TreeState(deep);
		tree.expandAll();
		await render(NodeTree, { target: frame, props: { tree, onopen: () => {} } });

		await expect.element(page.getByRole('treeitem').last()).toBeVisible();
		expect(frame.scrollWidth).toBeLessThanOrEqual(frame.clientWidth);
		frame.remove();
	});
});
