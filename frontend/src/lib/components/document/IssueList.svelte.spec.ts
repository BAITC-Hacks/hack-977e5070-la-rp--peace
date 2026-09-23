import { describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';

import '../../../routes/layout.css';

import type { IssueOut, NodeOut } from '$lib/api/document';
import { TreeState } from '$lib/document/tree-state.svelte';

import IssueList from './IssueList.svelte';
import NodeTree from './NodeTree.svelte';

function issue(
	id: number,
	nodeId: number | null,
	isBlocking: boolean,
	issueType: string,
	message: string
): IssueOut {
	return {
		id,
		node_id: nodeId,
		issue_type: issueType,
		message,
		is_blocking: isBlocking,
		resolved_at: null,
		created_at: '2026-09-23T10:00:00Z'
	};
}

function node(id: number, parentId: number | null, position: number, text: string): NodeOut {
	const marker = text.split(' ')[0];
	return {
		id,
		parent_id: parentId,
		position,
		node_type: parentId === null ? 'section' : 'clause',
		marker,
		text,
		source_start: 0,
		source_end: text.length,
		anchor: `п. ${marker}`,
		path: `п. ${marker}`,
		location: {}
	};
}

const ISSUES = [
	issue(1, null, false, 'uncovered_text', 'Текст после таблицы не попал ни в один пункт'),
	issue(2, 32, false, 'numbering_gap', 'После п. 3.2 идёт п. 3.4'),
	issue(3, null, true, 'other', 'Реквизит approved_on не принят: дата не в формате YYYY-MM-DD')
];

// Many sections so that п. 3.4 is far below the fold when the page opens.
const NODES = [
	...Array.from({ length: 30 }, (_, index) =>
		node(100 + index, null, index, `${index + 4} Раздел номер ${index + 4}`)
	),
	node(3, null, -1, '3 Структура и организация работы'),
	node(31, 3, 0, '3.1 Служба подчиняется Совету директоров.'),
	node(32, 3, 1, '3.4 Служба проводит аудит системы защиты информации.')
];

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

describe('IssueList', () => {
	it('lists blocking issues first, each with its type and message', async () => {
		const screen = await render(IssueList, { issues: ISSUES });

		const items = screen.getByRole('listitem').elements();
		expect(items.map((item) => item.querySelector('p')?.textContent)).toEqual([
			'Реквизит approved_on не принят: дата не в формате YYYY-MM-DD',
			'Текст после таблицы не попал ни в один пункт',
			'После п. 3.2 идёт п. 3.4'
		]);
		expect(items[0].textContent).toContain('Блокирующая');
		expect(items[0].textContent).toContain('Другое');
		expect(items[2].textContent).toContain('Предупреждение');
		expect(items[2].textContent).toContain('Пропуск в нумерации');
	});

	it('offers «К пункту» only for issues that point at a node', async () => {
		const onreveal = vi.fn();
		const screen = await render(IssueList, {
			issues: ISSUES,
			anchors: new Map([[32, 'п. 3.4']]),
			onreveal
		});

		const button = screen.getByRole('button', { name: 'К пункту' });
		expect(button.elements()).toHaveLength(1);
		await expect.element(button).toHaveAccessibleName('К пункту п. 3.4');
		await button.click();

		expect(onreveal).toHaveBeenCalledWith(32);
	});

	it('has no «К пункту» buttons without a handler', async () => {
		const screen = await render(IssueList, { issues: ISSUES });

		await expect.element(screen.getByRole('button', { name: 'К пункту' })).not.toBeInTheDocument();
	});

	it('says so when parsing found no problems', async () => {
		const screen = await render(IssueList, { issues: [] });

		await expect.element(screen.getByText('Проблем разбора не найдено.')).toBeVisible();
	});

	it('«К пункту» opens the node in the tree, selects it and brings it into view', async () => {
		const tree = new TreeState(NODES);
		tree.collapseAll();
		const treeScreen = await render(NodeTree, { tree });
		const issueScreen = await render(IssueList, {
			issues: ISSUES,
			anchors: new Map([[32, 'п. 3.4']]),
			onreveal: (nodeId: number) => tree.reveal(nodeId)
		});
		await expect.element(treeScreen.getByText('3.4 Служба проводит аудит')).not.toBeInTheDocument();

		await issueScreen.getByRole('button', { name: 'К пункту' }).click();

		const target = treeScreen.getByText('3.4 Служба проводит аудит');
		await expect.element(target).toBeVisible();
		await expect.element(target).toBeInViewport();
		const item = treeScreen.container.querySelector<HTMLElement>('[data-node-id="32"]');
		expect(item?.getAttribute('aria-selected')).toBe('true');
		await expect.element(item).toHaveFocus();
		const section = treeScreen.container.querySelector('[data-node-id="3"]');
		expect(section?.getAttribute('aria-expanded')).toBe('true');
	});

	it('wraps a long message and place within a phone screen', async () => {
		const frame = await phoneFrame();
		const place = 'after:dibr:2.8.8.8.8.8.8.8.8.8.1';
		const screen = await render(IssueList, {
			target: frame,
			props: {
				issues: [issue(1, 5, true, 'numbering_gap', `После п. 2.8 идёт ${LONG_WORD}`)],
				anchors: new Map([[5, place]]),
				onreveal: () => {}
			}
		});

		await expect.element(screen.getByText(place)).toBeVisible();
		expect(frame.scrollWidth).toBeLessThanOrEqual(frame.clientWidth);
		frame.remove();
	});
});
