import type { NodeOut } from '$lib/api/document';

/** A node with its children in document order. */
export interface TreeNode {
	readonly node: NodeOut;
	readonly children: TreeNode[];
	readonly parent: TreeNode | null;
	/** 0 for top-level nodes. */
	readonly depth: number;
}

export interface DocumentTree {
	readonly roots: TreeNode[];
	readonly byId: ReadonlyMap<number, TreeNode>;
}

function byPosition(a: NodeOut, b: NodeOut): number {
	return a.position - b.position || a.id - b.id;
}

/**
 * Builds the document tree from the flat `GET /nodes` list: children by `parent_id`, ordered by
 * `position`. A node whose parent is missing becomes a top-level node rather than disappearing.
 */
export function buildTree(nodes: readonly NodeOut[]): DocumentTree {
	const ids = new Set(nodes.map((node) => node.id));
	const childrenOf = new Map<number | null, NodeOut[]>();
	for (const node of nodes) {
		const parentId = node.parent_id !== null && ids.has(node.parent_id) ? node.parent_id : null;
		const siblings = childrenOf.get(parentId) ?? [];
		siblings.push(node);
		childrenOf.set(parentId, siblings);
	}
	for (const siblings of childrenOf.values()) {
		siblings.sort(byPosition);
	}

	const byId = new Map<number, TreeNode>();
	const attach = (node: NodeOut, parent: TreeNode | null): TreeNode => {
		const item: TreeNode = { node, children: [], parent, depth: parent ? parent.depth + 1 : 0 };
		byId.set(node.id, item);
		for (const child of childrenOf.get(node.id) ?? []) {
			// Parent links that loop never reach a root; they are attached below instead.
			if (!byId.has(child.id)) {
				item.children.push(attach(child, item));
			}
		}
		return item;
	};
	const roots = (childrenOf.get(null) ?? []).map((node) => attach(node, null));
	for (const node of [...nodes].sort(byPosition)) {
		if (!byId.has(node.id)) {
			roots.push(attach(node, null));
		}
	}
	return { roots, byId };
}

/** Ids of the node's ancestors, from the top level down to its parent. */
export function ancestorIds(tree: DocumentTree, id: number): number[] {
	const ids: number[] = [];
	for (let item = tree.byId.get(id)?.parent; item; item = item.parent) {
		ids.unshift(item.node.id);
	}
	return ids;
}

/** Nodes a reader sees, in reading order: everything whose ancestors are all expanded. */
export function visibleNodes(
	roots: readonly TreeNode[],
	isExpanded: (id: number) => boolean
): TreeNode[] {
	const visible: TreeNode[] = [];
	const walk = (items: readonly TreeNode[]) => {
		for (const item of items) {
			visible.push(item);
			if (item.children.length > 0 && isExpanded(item.node.id)) {
				walk(item.children);
			}
		}
	};
	walk(roots);
	return visible;
}

/** Text longer than this is folded in the tree until the reader asks for all of it. */
export const EXCERPT_LENGTH = 280;

/** The start of a long text, cut at a word boundary, or the whole text if it is short. */
export function excerpt(text: string, limit = EXCERPT_LENGTH): { text: string; clipped: boolean } {
	if (text.length <= limit) {
		return { text, clipped: false };
	}
	const head = text.slice(0, limit);
	const space = head.lastIndexOf(' ');
	const cut = space > limit / 2 ? head.slice(0, space) : head;
	return { text: `${cut.trimEnd()}…`, clipped: true };
}
