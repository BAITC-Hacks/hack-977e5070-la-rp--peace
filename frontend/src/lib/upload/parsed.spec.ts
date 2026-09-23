import { describe, expect, it } from 'vitest';

import type { DocSet, DocumentOut } from '$lib/api/types';

import { comparePair, parsedDocuments } from './parsed';

function item(set: DocSet, id: number, parsed = true) {
	const document = { id } as DocumentOut;
	return { set, file: new File([], `${set}-${id}.docx`), document, parsed };
}

describe('parsedDocuments', () => {
	it('lists «До», then «После», then the external sets, each in upload order', () => {
		const items = [
			item('regulatory', 5),
			item('after', 2),
			item('before', 1),
			item('after', 3),
			item('benchmark', 4)
		];

		expect(parsedDocuments(items).map((doc) => doc.id)).toEqual([1, 2, 3, 5, 4]);
		expect(parsedDocuments(items)[0]).toEqual({ id: 1, set: 'before', name: 'before-1.docx' });
	});

	it('leaves out files whose parse has not ended', () => {
		expect(parsedDocuments([item('before', 1, false), item('after', 2)])).toEqual([
			{ id: 2, set: 'after', name: 'after-2.docx' }
		]);
		expect(parsedDocuments([{ ...item('before', 1), document: null }])).toEqual([]);
	});
});

describe('comparePair', () => {
	it('pairs the first parsed «До» with the first parsed «После»', () => {
		const documents = parsedDocuments([
			item('regulatory', 5),
			item('after', 2),
			item('before', 1),
			item('after', 3)
		]);

		expect(comparePair(documents)).toEqual({ before: 1, after: 2 });
	});

	it('gives null until both sides are parsed', () => {
		expect(comparePair(parsedDocuments([item('before', 1), item('after', 2, false)]))).toBeNull();
		expect(comparePair([])).toBeNull();
	});
});
