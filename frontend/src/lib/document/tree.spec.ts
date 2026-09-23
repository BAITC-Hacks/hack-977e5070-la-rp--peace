import { describe, expect, it } from 'vitest';

import type { NodeOut } from '$lib/api/document';

import { ancestorIds, buildTree, excerpt, visibleNodes } from './tree';

function node(id: number, parentId: number | null, position: number): NodeOut {
	return {
		id,
		parent_id: parentId,
		position,
		node_type: parentId === null ? 'section' : 'clause',
		marker: String(id),
		text: `Узел ${id}`,
		source_start: 0,
		source_end: 0,
		anchor: `п. ${id}`,
		path: `п. ${id}`,
		location: {}
	};
}

// Разд. 1 › п. 3 (› подп. 5), п. 4; разд. 2 — listed out of order, as a database may return them.
const NODES = [node(4, 1, 1), node(2, null, 1), node(5, 3, 0), node(1, null, 0), node(3, 1, 0)];

const ids = (items: { node: NodeOut }[]) => items.map((item) => item.node.id);

describe('buildTree', () => {
	it('nests nodes by parent_id and orders siblings by position', () => {
		const tree = buildTree(NODES);

		expect(ids(tree.roots)).toEqual([1, 2]);
		expect(ids(tree.roots[0].children)).toEqual([3, 4]);
		expect(ids(tree.roots[0].children[0].children)).toEqual([5]);
		expect(tree.byId.get(5)?.depth).toBe(2);
		expect(tree.byId.get(5)?.parent?.node.id).toBe(3);
		expect(tree.byId.size).toBe(5);
	});

	it('keeps a node whose parent is missing as a top-level node', () => {
		const tree = buildTree([node(1, null, 0), node(7, 99, 1)]);

		expect(ids(tree.roots)).toEqual([1, 7]);
		expect(tree.byId.get(7)?.depth).toBe(0);
	});

	it('keeps every node when parent links loop', () => {
		const tree = buildTree([node(1, 2, 0), node(2, 1, 1)]);

		expect(tree.byId.size).toBe(2);
		expect(ids(tree.roots)).toEqual([1]);
		expect(ids(tree.roots[0].children)).toEqual([2]);
	});

	it('returns an empty tree for no nodes', () => {
		expect(buildTree([])).toEqual({ roots: [], byId: new Map() });
	});
});

describe('ancestorIds', () => {
	it('lists ancestors from the top level down', () => {
		const tree = buildTree(NODES);

		expect(ancestorIds(tree, 5)).toEqual([1, 3]);
		expect(ancestorIds(tree, 1)).toEqual([]);
		expect(ancestorIds(tree, 404)).toEqual([]);
	});
});

describe('visibleNodes', () => {
	it('shows children of expanded nodes only', () => {
		const tree = buildTree(NODES);

		expect(ids(visibleNodes(tree.roots, () => false))).toEqual([1, 2]);
		expect(ids(visibleNodes(tree.roots, (id) => id === 1))).toEqual([1, 3, 4, 2]);
		expect(ids(visibleNodes(tree.roots, () => true))).toEqual([1, 3, 5, 4, 2]);
	});

	it('hides descendants of a collapsed node even if they are expanded', () => {
		const tree = buildTree(NODES);

		expect(ids(visibleNodes(tree.roots, (id) => id === 3))).toEqual([1, 2]);
	});
});

describe('excerpt', () => {
	it('keeps short text whole', () => {
		expect(excerpt('Проводит аудит.', 20)).toEqual({ text: 'Проводит аудит.', clipped: false });
	});

	it('cuts long text at a word boundary', () => {
		expect(excerpt('Проводит аудит системы защиты информации', 24)).toEqual({
			text: 'Проводит аудит системы…',
			clipped: true
		});
	});

	it('cuts inside a word when the text has no early space', () => {
		expect(excerpt('Сверхдлинноеслово и хвост', 10)).toEqual({
			text: 'Сверхдлинн…',
			clipped: true
		});
	});
});
