// Geometry of the arrows between the «до» column, the finding cards and the «после» column
// (docs/spec/visual_compare.html). Pure: takes measured boxes, returns SVG path data.

import type { Finding, FindingType } from '$lib/result/types';

/** A rectangle in pixels from the row's top-left corner. */
export interface Box {
	left: number;
	top: number;
	right: number;
	bottom: number;
}

/** Where everything in one block row is, relative to the row. */
export interface RowLayout {
	before: Box;
	after: Box;
	/** Card boxes by finding id. */
	cards: ReadonlyMap<string, Box>;
	/** Column item boxes by item id. */
	items: ReadonlyMap<string, Box>;
}

/** `from`: «до» item → card; `to`: card → «после» item; `also`: dashed `to`; `loss`: stub to nowhere. */
export type ArrowKind = 'from' | 'to' | 'also' | 'loss';

export interface Arrow {
	key: string;
	finding: string;
	type: FindingType;
	kind: ArrowKind;
	d: string;
	width: number;
	dash: string | null;
	/** Arrowhead at the end; only arrows into the «после» column have one. */
	head: boolean;
}

/** Anchor (left end of the baseline) of the «∅ не закреплено» label next to a loss. */
export interface LossMark {
	finding: string;
	x: number;
	y: number;
}

export interface RowArrows {
	arrows: Arrow[];
	marks: LossMark[];
}

/** Arrows stop short of the «после» column so the arrowhead stays visible. */
const HEAD_GAP = 2;
const LOSS_STUB = 34;
const LOSS_LABEL_DX = 40;
const LOSS_LABEL_DY = 4;

const round = (value: number) => Math.round(value * 10) / 10;

const middle = (box: Box) => (box.top + box.bottom) / 2;

/** Horizontal S-curve from (x1, y1) to (x2, y2). */
export function curve(x1: number, y1: number, x2: number, y2: number): string {
	const dx = (x2 - x1) / 2;
	const [a, b, c, d] = [x1, y1, x2, y2].map(round);
	return `M${a},${b} C${round(x1 + dx)},${b} ${round(x2 - dx)},${d} ${c},${d}`;
}

function linked(
	finding: Finding,
	kind: 'from' | 'to' | 'also',
	ids: readonly string[],
	layout: RowLayout,
	card: Box
): Arrow[] {
	const y = middle(card);
	const width = kind === 'also' ? 1.5 : finding.type === 'kept' ? 1.2 : 2;
	return ids.flatMap((id) => {
		const item = layout.items.get(id);
		if (item === undefined) {
			return [];
		}
		const d =
			kind === 'from'
				? curve(layout.before.right, middle(item), card.left, y)
				: curve(card.right, y, layout.after.left - HEAD_GAP, middle(item));
		return [
			{
				key: `${finding.id}:${kind}:${id}`,
				finding: finding.id,
				type: finding.type,
				kind,
				d,
				width,
				dash: kind === 'also' ? '5 4' : null,
				head: kind !== 'from'
			}
		];
	});
}

function lossStub(finding: Finding, card: Box): Arrow {
	const x = round(card.right);
	const y = round(middle(card));
	return {
		key: `${finding.id}:loss`,
		finding: finding.id,
		type: finding.type,
		kind: 'loss',
		d: `M${x},${y} L${round(x + LOSS_STUB)},${y}`,
		width: 2,
		dash: '3 3',
		head: false
	};
}

/** Arrows of the row's findings; items or cards missing from the layout are skipped. */
export function layoutArrows(findings: readonly Finding[], layout: RowLayout): RowArrows {
	const arrows: Arrow[] = [];
	const marks: LossMark[] = [];
	for (const finding of findings) {
		const card = layout.cards.get(finding.id);
		if (card === undefined) {
			continue;
		}
		arrows.push(
			...linked(finding, 'from', finding.from, layout, card),
			...linked(finding, 'to', finding.to, layout, card),
			...linked(finding, 'also', finding.also ?? [], layout, card)
		);
		if (finding.type === 'loss') {
			arrows.push(lossStub(finding, card));
			marks.push({
				finding: finding.id,
				x: round(card.right + LOSS_LABEL_DX),
				y: round(middle(card) + LOSS_LABEL_DY)
			});
		}
	}
	return { arrows, marks };
}
