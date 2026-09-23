import { describe, expect, it } from 'vitest';

import type { Finding } from '$lib/result/types';

import { type Box, type RowLayout, curve, layoutArrows } from './arrows';

function finding(id: string, overrides: Partial<Finding>): Finding {
	return {
		id,
		type: 'moved',
		block: 'ИБ и режим',
		title: 'Перенесено',
		from: [],
		to: [],
		evidence: { conclusion: 'Вывод', method: 'Метод', steps: [], confidence: 'high' },
		review: null,
		...overrides
	};
}

/** A box `height` pixels tall whose vertical middle is at `y`. */
function box(left: number, right: number, y: number, height = 20): Box {
	return { left, right, top: y - height / 2, bottom: y + height / 2 };
}

// «до» column 0..300, cards 350..650, «после» column 700..1000.
function layout(cards: Record<string, number>, items: Record<string, number>): RowLayout {
	return {
		before: { left: 0, right: 300, top: 0, bottom: 400 },
		after: { left: 700, right: 1000, top: 0, bottom: 400 },
		cards: new Map(Object.entries(cards).map(([id, y]) => [id, box(350, 650, y, 60)])),
		items: new Map(
			Object.entries(items).map(([id, y]) => [
				id,
				id.startsWith('b') ? box(0, 300, y) : box(700, 1000, y)
			])
		)
	};
}

describe('curve', () => {
	it('bends horizontally halfway between the ends', () => {
		expect(curve(0, 10, 100, 50)).toBe('M0,10 C50,10 50,50 100,50');
	});

	it('rounds to a tenth of a pixel', () => {
		expect(curve(0.123, 1.06, 10.01, 2)).toBe('M0.1,1.1 C5.1,1.1 5.1,2 10,2');
	});
});

describe('layoutArrows', () => {
	it('draws from the «до» column to the card without a head, and on to «после» with one', () => {
		const merge = finding('C-001', { type: 'transformed', from: ['b_dib'], to: ['a_dibr'] });

		const { arrows, marks } = layoutArrows(
			[merge],
			layout({ 'C-001': 100 }, { b_dib: 40, a_dibr: 160 })
		);

		expect(arrows).toEqual([
			{
				key: 'C-001:from:b_dib',
				finding: 'C-001',
				type: 'transformed',
				kind: 'from',
				d: curve(300, 40, 350, 100),
				width: 2,
				dash: null,
				head: false
			},
			{
				key: 'C-001:to:a_dibr',
				finding: 'C-001',
				type: 'transformed',
				kind: 'to',
				d: curve(650, 100, 698, 160),
				width: 2,
				dash: null,
				head: true
			}
		]);
		expect(marks).toEqual([]);
	});

	it('draws one arrow per linked item and `also` dashed with a head', () => {
		const conflict = finding('C-010', {
			type: 'conflict',
			from: ['b_audit'],
			to: ['a_audit'],
			also: ['a_prot']
		});

		const { arrows } = layoutArrows(
			[conflict],
			layout({ 'C-010': 200 }, { b_audit: 200, a_audit: 250, a_prot: 50 })
		);

		expect(arrows.map((arrow) => [arrow.kind, arrow.dash, arrow.head])).toEqual([
			['from', null, false],
			['to', null, true],
			['also', '5 4', true]
		]);
		expect(arrows[2].d).toBe(curve(650, 200, 698, 50));
		expect(arrows[2].width).toBe(1.5);
	});

	it('draws kept findings thinner', () => {
		const kept = finding('C-004', { type: 'kept', from: ['b_it'], to: ['a_it'] });

		const { arrows } = layoutArrows([kept], layout({ 'C-004': 100 }, { b_it: 100, a_it: 100 }));

		expect(arrows.map((arrow) => arrow.width)).toEqual([1.2, 1.2]);
	});

	it('ends a loss in a dashed stub with the «не закреплено» label', () => {
		const loss = finding('C-011', { type: 'loss', from: ['b_mob'], to: [] });

		const { arrows, marks } = layoutArrows([loss], layout({ 'C-011': 300 }, { b_mob: 120 }));

		expect(arrows.map((arrow) => arrow.kind)).toEqual(['from', 'loss']);
		expect(arrows[1]).toMatchObject({ d: 'M650,300 L684,300', dash: '3 3', head: false });
		expect(marks).toEqual([{ finding: 'C-011', x: 690, y: 304 }]);
	});

	it('skips cards and items that are not rendered', () => {
		const shown = finding('C-001', { from: ['b_gone', 'b_here'], to: ['a_gone'] });
		const hidden = finding('C-002', { from: ['b_here'] });

		const { arrows } = layoutArrows([shown, hidden], layout({ 'C-001': 100 }, { b_here: 100 }));

		expect(arrows.map((arrow) => arrow.key)).toEqual(['C-001:from:b_here']);
	});
});
