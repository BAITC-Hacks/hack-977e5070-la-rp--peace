import { describe, expect, it } from 'vitest';

import type { NodeOut } from '$lib/api/document';

import { TreeState } from './tree-state.svelte';

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

// 1 › 3 › 5, 1 › 4, and 2 without children.
const NODES = [node(1, null, 0), node(3, 1, 0), node(5, 3, 0), node(4, 1, 1), node(2, null, 1)];

const visibleIds = (state: TreeState) => state.visible.map((item) => item.node.id);

describe('TreeState', () => {
	it('starts with top-level nodes that have children expanded', () => {
		const state = new TreeState(NODES);

		expect([...state.expanded]).toEqual([1]);
		expect(visibleIds(state)).toEqual([1, 3, 4, 2]);
		expect(state.activeId).toBe(1);
	});

	it('toggles only nodes that have children', () => {
		const state = new TreeState(NODES);

		state.toggle(3);
		state.toggle(4);
		expect(visibleIds(state)).toEqual([1, 3, 5, 4, 2]);

		state.toggle(1);
		expect(visibleIds(state)).toEqual([1, 2]);
		expect(state.expanded.has(4)).toBe(false);
	});

	it('expands and collapses everything', () => {
		const state = new TreeState(NODES);

		state.expandAll();
		expect(visibleIds(state)).toEqual([1, 3, 5, 4, 2]);

		state.collapseAll();
		expect(visibleIds(state)).toEqual([1, 2]);
	});

	it('hands focus to the outermost collapsed ancestor of a hidden selected node', () => {
		const state = new TreeState(NODES);
		state.reveal(5);

		state.toggle(3);
		expect(state.activeId).toBe(3);

		state.collapseAll();
		expect(state.activeId).toBe(1);
		expect(state.selectedId).toBe(5);
	});

	it('shows and folds the full text of a node', () => {
		const state = new TreeState(NODES);

		state.toggleText(5);
		expect(state.fullText.has(5)).toBe(true);
		state.toggleText(5);
		expect(state.fullText.has(5)).toBe(false);
	});
});

describe('TreeState.reveal', () => {
	it('expands the ancestors and selects the node', () => {
		const state = new TreeState(NODES);
		state.collapseAll();

		expect(state.reveal(5)).toBe(true);

		expect(visibleIds(state)).toEqual([1, 3, 5, 4, 2]);
		expect(state.selectedId).toBe(5);
		expect(state.activeId).toBe(5);
		expect(state.revealed).toEqual({ id: 5 });
	});

	it('asks to scroll again when the node is revealed twice', () => {
		const state = new TreeState(NODES);
		state.reveal(4);
		const first = state.revealed;

		state.reveal(4);

		expect(state.revealed).not.toBe(first);
	});

	it('ignores a node that is not in the tree', () => {
		const state = new TreeState(NODES);

		expect(state.reveal(404)).toBe(false);
		expect(state.selectedId).toBeNull();
		expect(state.revealed).toBeNull();
	});
});

describe('TreeState.navigate', () => {
	it('moves through visible nodes with arrows, Home and End', () => {
		const state = new TreeState(NODES);

		expect(state.navigate('ArrowDown', 1)).toBe(3);
		expect(state.navigate('ArrowDown', 3)).toBe(4);
		expect(state.navigate('ArrowUp', 4)).toBe(3);
		expect(state.navigate('End', 3)).toBe(2);
		expect(state.navigate('ArrowDown', 2)).toBe(2);
		expect(state.navigate('Home', 2)).toBe(1);
		expect(state.navigate('ArrowUp', 1)).toBe(1);
		expect(state.selectedId).toBe(1);
	});

	it('expands with ArrowRight, then steps into the first child', () => {
		const state = new TreeState(NODES);

		expect(state.navigate('ArrowRight', 3)).toBe(3);
		expect(state.expanded.has(3)).toBe(true);
		expect(state.navigate('ArrowRight', 3)).toBe(5);
		expect(state.navigate('ArrowRight', 5)).toBe(5);
	});

	it('collapses with ArrowLeft, then steps out to the parent', () => {
		const state = new TreeState(NODES);
		state.expandAll();

		expect(state.navigate('ArrowLeft', 5)).toBe(3);
		expect(state.navigate('ArrowLeft', 3)).toBe(3);
		expect(state.expanded.has(3)).toBe(false);
		expect(state.navigate('ArrowLeft', 3)).toBe(1);
		expect(state.navigate('ArrowLeft', 2)).toBe(2);
	});

	it('toggles with Enter and Space', () => {
		const state = new TreeState(NODES);

		expect(state.navigate('Enter', 1)).toBe(1);
		expect(state.expanded.has(1)).toBe(false);
		expect(state.navigate(' ', 1)).toBe(1);
		expect(state.expanded.has(1)).toBe(true);
	});

	it('leaves other keys and unknown nodes alone', () => {
		const state = new TreeState(NODES);

		expect(state.navigate('a', 1)).toBeNull();
		expect(state.navigate('ArrowDown', 404)).toBeNull();
		expect(state.selectedId).toBeNull();
	});
});
