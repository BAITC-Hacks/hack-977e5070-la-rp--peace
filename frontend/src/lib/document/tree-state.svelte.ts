import { SvelteSet } from 'svelte/reactivity';

import type { NodeOut } from '$lib/api/document';

import { ancestorIds, buildTree, visibleNodes, type DocumentTree, type TreeNode } from './tree';

/** What the document tree shows: expanded nodes, the selected node and fully shown texts. */
export class TreeState {
	readonly tree: DocumentTree;
	readonly expanded = new SvelteSet<number>();
	/** Nodes whose long text is shown in full. */
	readonly fullText = new SvelteSet<number>();
	selectedId = $state<number | null>(null);
	/** Replaced on every `reveal`, so the view scrolls to the node even if it is already selected. */
	revealed = $state.raw<{ id: number } | null>(null);
	readonly visible: TreeNode[] = $derived.by(() =>
		visibleNodes(this.tree.roots, (id) => this.expanded.has(id))
	);

	/** Top-level nodes start expanded, so the reader sees sections with their clauses. */
	constructor(nodes: readonly NodeOut[]) {
		this.tree = buildTree(nodes);
		for (const root of this.tree.roots) {
			if (root.children.length > 0) {
				this.expanded.add(root.node.id);
			}
		}
	}

	/**
	 * The node that takes keyboard focus when the tree is tabbed into: the selected one, or its
	 * outermost collapsed ancestor while a collapsed branch hides it.
	 */
	get activeId(): number | null {
		const id = this.selectedId;
		if (id === null) {
			return this.tree.roots[0]?.node.id ?? null;
		}
		return ancestorIds(this.tree, id).find((ancestor) => !this.expanded.has(ancestor)) ?? id;
	}

	toggle(id: number): void {
		if (this.expanded.has(id)) {
			this.expanded.delete(id);
		} else if (this.tree.byId.get(id)?.children.length) {
			this.expanded.add(id);
		}
	}

	expandAll(): void {
		for (const item of this.tree.byId.values()) {
			if (item.children.length > 0) {
				this.expanded.add(item.node.id);
			}
		}
	}

	collapseAll(): void {
		this.expanded.clear();
	}

	toggleText(id: number): void {
		if (!this.fullText.delete(id)) {
			this.fullText.add(id);
		}
	}

	/** Selects a node and expands its ancestors so it is on screen; false if there is no such node. */
	reveal(id: number): boolean {
		if (!this.tree.byId.has(id)) {
			return false;
		}
		for (const ancestor of ancestorIds(this.tree, id)) {
			this.expanded.add(ancestor);
		}
		this.selectedId = id;
		this.revealed = { id };
		return true;
	}

	/**
	 * Applies a key of the WAI-ARIA tree pattern to the node `fromId` and selects the node that
	 * should take focus. Returns its id, or null when the key is not a tree command.
	 */
	navigate(key: string, fromId: number): number | null {
		const item = this.tree.byId.get(fromId);
		if (item === undefined) {
			return null;
		}
		const index = this.visible.indexOf(item);
		const expandable = item.children.length > 0;
		const expanded = this.expanded.has(fromId);
		let target: TreeNode | undefined;
		switch (key) {
			case 'ArrowDown':
				target = this.visible[index + 1] ?? item;
				break;
			case 'ArrowUp':
				target = this.visible[index - 1] ?? item;
				break;
			case 'Home':
				target = this.visible[0];
				break;
			case 'End':
				target = this.visible.at(-1);
				break;
			case 'ArrowRight':
				if (expandable && !expanded) {
					this.expanded.add(fromId);
					target = item;
				} else {
					target = expanded ? item.children[0] : item;
				}
				break;
			case 'ArrowLeft':
				if (expanded) {
					this.expanded.delete(fromId);
					target = item;
				} else {
					target = item.parent ?? item;
				}
				break;
			case 'Enter':
			case ' ':
				this.toggle(fromId);
				target = item;
				break;
			default:
				return null;
		}
		const id = (target ?? item).node.id;
		this.selectedId = id;
		return id;
	}
}
