import type { NodeOut } from '$lib/api/document';
import { buildTree, type TreeNode } from '$lib/document/tree';

/**
 * What happened to a node between the documents. A node moved to another parent is shown as
 * `removed` + `added` for now (open question 3 in docs/spec/tz_site.md §10).
 */
export type RowStatus = 'unchanged' | 'changed' | 'removed' | 'added';

/** One line of the Word view: a node of «до», of «после», or a pair of them. */
export interface DiffRow {
	readonly status: RowStatus;
	readonly before: NodeOut | null;
	readonly after: NodeOut | null;
	/** Nesting level: 0 for a top-level node, 1 for its children and so on. */
	readonly depth: number;
}

/** A top-level section of the documents with everything under it. */
export interface DiffBlock {
	/** The top-level node opening the block; null for top-level text outside any section. */
	readonly head: DiffRow | null;
	/** Rows under the head (or the loose top-level rows), in reading order. */
	readonly rows: DiffRow[];
}

/** Word similarity (0…1) two nodes without a common marker need to be taken as one node. */
export const SIMILARITY_THRESHOLD = 0.5;

/**
 * Most sibling pairs whose similarity is computed. Above it only nodes with the same marker or
 * the same text are paired, so a huge flat document stays responsive.
 */
export const MAX_COMPARED_PAIRS = 250_000;

/** Separator between the levels of `NodeOut.path`, e.g. «Разд. 3 «…» › п. 3.4 › подп. «а»». */
const PATH_SEPARATOR = ' › ';
const WORD = /[\p{L}\p{N}]+/gu;
const WHITESPACE = /\s+/g;

function normalize(text: string): string {
	return text.replace(WHITESPACE, ' ').trim();
}

/** Words of the text as a multiset, without the node's own number («3.4.», «а)»). */
function wordsOf(node: NodeOut): Map<string, number> {
	const text =
		node.marker !== null && node.text.startsWith(node.marker)
			? node.text.slice(node.marker.length)
			: node.text;
	const words = new Map<string, number>();
	for (const word of text.toLowerCase().match(WORD) ?? []) {
		words.set(word, (words.get(word) ?? 0) + 1);
	}
	return words;
}

/** Dice coefficient of two word multisets: 1 for the same words, 0 for none in common. */
function dice(a: ReadonlyMap<string, number>, b: ReadonlyMap<string, number>): number {
	let sizeA = 0;
	let sizeB = 0;
	let common = 0;
	for (const count of b.values()) {
		sizeB += count;
	}
	for (const [word, count] of a) {
		sizeA += count;
		common += Math.min(count, b.get(word) ?? 0);
	}
	return sizeA + sizeB === 0 ? 1 : (2 * common) / (sizeA + sizeB);
}

/** Word similarity of two nodes' texts, ignoring case, punctuation and the nodes' own numbers. */
export function textSimilarity(a: NodeOut, b: NodeOut): number {
	return dice(wordsOf(a), wordsOf(b));
}

/**
 * How a node is found among its siblings on the other side: its marker («3.4», «а»), else the
 * last level of its path («абз. 2»). A key shared by two siblings identifies neither, so it is
 * dropped.
 */
function siblingKeys(nodes: readonly TreeNode[]): (string | null)[] {
	const candidates = nodes.map(({ node }) => {
		const label = node.path.split(PATH_SEPARATOR).at(-1)?.trim();
		return {
			marker: node.marker ? `marker:${node.marker}` : null,
			label: label ? `path:${label}` : null
		};
	});
	const counts = new Map<string, number>();
	for (const { marker, label } of candidates) {
		for (const key of [marker, label]) {
			if (key !== null) {
				counts.set(key, (counts.get(key) ?? 0) + 1);
			}
		}
	}
	const unique = (key: string | null) => (key !== null && counts.get(key) === 1 ? key : null);
	return candidates.map(({ marker, label }) => unique(marker) ?? unique(label));
}

/**
 * Pairs the children of two matched parents; returns the partner in `after` of every node in
 * `before`, or -1.
 *
 * 1. Nodes with the same key (marker, else path level) are paired, unless the text of either
 *    one matches another sibling better and at least `SIMILARITY_THRESHOLD` — that is how
 *    renumbered clauses are recognised instead of being paired by their new numbers.
 * 2. The rest are paired by text similarity, most similar first, if it reaches the threshold.
 */
function pairSiblings(before: readonly TreeNode[], after: readonly TreeNode[]): number[] {
	const n = before.length;
	const m = after.length;
	const partner = new Array<number>(n).fill(-1);
	const taken = new Array<boolean>(m).fill(false);

	const wordsBefore = before.map(({ node }) => wordsOf(node));
	const wordsAfter = after.map(({ node }) => wordsOf(node));
	const measured = n * m <= MAX_COMPARED_PAIRS;
	const scores = new Float64Array(measured ? n * m : 0);
	const bestOfBefore = new Float64Array(n);
	const bestOfAfter = new Float64Array(m);
	if (measured) {
		for (let i = 0; i < n; i++) {
			for (let j = 0; j < m; j++) {
				const score = dice(wordsBefore[i], wordsAfter[j]);
				scores[i * m + j] = score;
				bestOfBefore[i] = Math.max(bestOfBefore[i], score);
				bestOfAfter[j] = Math.max(bestOfAfter[j], score);
			}
		}
	}
	const score = (i: number, j: number) =>
		measured ? scores[i * m + j] : dice(wordsBefore[i], wordsAfter[j]);
	const beaten = (best: number, own: number) => best > own && best >= SIMILARITY_THRESHOLD;

	const keysAfter = new Map<string, number>();
	siblingKeys(after).forEach((key, j) => {
		if (key !== null) {
			keysAfter.set(key, j);
		}
	});
	siblingKeys(before).forEach((key, i) => {
		const j = key === null ? undefined : keysAfter.get(key);
		if (j === undefined) {
			return;
		}
		const own = score(i, j);
		if (measured && (beaten(bestOfBefore[i], own) || beaten(bestOfAfter[j], own))) {
			return;
		}
		partner[i] = j;
		taken[j] = true;
	});

	const candidates: { i: number; j: number; score: number }[] = [];
	if (measured) {
		for (let i = 0; i < n; i++) {
			for (let j = 0; j < m; j++) {
				if (partner[i] === -1 && !taken[j] && scores[i * m + j] >= SIMILARITY_THRESHOLD) {
					candidates.push({ i, j, score: scores[i * m + j] });
				}
			}
		}
	} else {
		const byText = new Map<string, number[]>();
		after.forEach(({ node }, j) => {
			if (!taken[j]) {
				const text = normalize(node.text);
				byText.set(text, [...(byText.get(text) ?? []), j]);
			}
		});
		before.forEach(({ node }, i) => {
			for (const j of partner[i] === -1 ? (byText.get(normalize(node.text)) ?? []) : []) {
				candidates.push({ i, j, score: 1 });
			}
		});
	}
	candidates.sort((x, y) => y.score - x.score || x.i - y.i || x.j - y.j);
	for (const { i, j } of candidates) {
		if (partner[i] === -1 && !taken[j]) {
			partner[i] = j;
			taken[j] = true;
		}
	}
	return partner;
}

type Entry =
	| { before: TreeNode; after: TreeNode }
	| { before: TreeNode; after: null }
	| { before: null; after: TreeNode };

/**
 * Siblings of both sides in one reading order: the order of «после», with each unpaired node of
 * «до» placed before the additions of the gap it was in, as a reader of tracked changes expects.
 */
function alignSiblings(before: readonly TreeNode[], after: readonly TreeNode[]): Entry[] {
	const partner = pairSiblings(before, after);
	const partnerOfAfter = new Array<number>(after.length).fill(-1);
	partner.forEach((j, i) => {
		if (j !== -1) {
			partnerOfAfter[j] = i;
		}
	});
	// For each position in «после», the «до» partner of the next paired node from there on.
	const upcoming = new Array<number>(after.length + 1).fill(before.length);
	for (let j = after.length - 1; j >= 0; j--) {
		upcoming[j] = partnerOfAfter[j] === -1 ? upcoming[j + 1] : partnerOfAfter[j];
	}

	const entries: Entry[] = [];
	let next = 0;
	const flushRemoved = (limit: number) => {
		for (; next < limit; next++) {
			if (partner[next] === -1) {
				entries.push({ before: before[next], after: null });
			}
		}
	};
	after.forEach((item, j) => {
		flushRemoved(upcoming[j]);
		const i = partnerOfAfter[j];
		if (i === -1) {
			entries.push({ before: null, after: item });
		} else {
			entries.push({ before: before[i], after: item });
			next = Math.max(next, i + 1);
		}
	});
	flushRemoved(before.length);
	return entries;
}

function statusOf(entry: Entry): RowStatus {
	if (entry.before === null) {
		return 'added';
	}
	if (entry.after === null) {
		return 'removed';
	}
	return normalize(entry.before.node.text) === normalize(entry.after.node.text)
		? 'unchanged'
		: 'changed';
}

function rowOf(entry: Entry, depth: number): DiffRow {
	return {
		status: statusOf(entry),
		before: entry.before?.node ?? null,
		after: entry.after?.node ?? null,
		depth
	};
}

/** Rows of everything under `entry`, depth first; one-sided entries take their subtree along. */
function descendantRows(entry: Entry, depth: number): DiffRow[] {
	const children = alignSiblings(entry.before?.children ?? [], entry.after?.children ?? []);
	return children.flatMap((child) => [rowOf(child, depth), ...descendantRows(child, depth + 1)]);
}

/** Top-level nodes that open a block of their own rather than being loose text. */
function opensBlock(entry: Entry): boolean {
	return [entry.before, entry.after].some(
		(item) =>
			item !== null &&
			(item.children.length > 0 ||
				item.node.node_type === 'section' ||
				item.node.node_type === 'heading')
	);
}

/**
 * Aligns the nodes of two documents for the Word view. Nodes are paired level by level: the
 * children of paired parents first by marker and path, then by text similarity (see
 * `pairSiblings`). The result is grouped by the documents' own top-level sections; consecutive
 * top-level text outside sections forms a block without a head.
 */
export function alignDocuments(before: readonly NodeOut[], after: readonly NodeOut[]): DiffBlock[] {
	const top = alignSiblings(buildTree(before).roots, buildTree(after).roots);
	const blocks: DiffBlock[] = [];
	for (const entry of top) {
		if (opensBlock(entry)) {
			blocks.push({ head: rowOf(entry, 0), rows: descendantRows(entry, 1) });
			continue;
		}
		const last = blocks.at(-1);
		if (last !== undefined && last.head === null) {
			last.rows.push(rowOf(entry, 0));
		} else {
			blocks.push({ head: null, rows: [rowOf(entry, 0)] });
		}
	}
	return blocks;
}
