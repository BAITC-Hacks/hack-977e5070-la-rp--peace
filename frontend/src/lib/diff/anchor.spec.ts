import { describe, expect, it } from 'vitest';

import {
	compareHref,
	compareQuery,
	nodeAnchorId,
	parseCompareParams,
	parseNodeHash
} from './anchor';

describe('parseCompareParams', () => {
	it('reads both document ids', () => {
		expect(parseCompareParams(new URLSearchParams('before=7&after=12'))).toEqual({
			before: 7,
			after: 12
		});
	});

	it('gives null for a missing or malformed id', () => {
		expect(parseCompareParams(new URLSearchParams('before=abc'))).toEqual({
			before: null,
			after: null
		});
	});
});

describe('compareQuery', () => {
	it('builds the query parseCompareParams reads back', () => {
		const query = compareQuery(7, 12);

		expect(query).toBe('?before=7&after=12');
		expect(parseCompareParams(new URLSearchParams(query))).toEqual({ before: 7, after: 12 });
	});
});

describe('compareHref', () => {
	it('links to the Word view of both documents at the node', () => {
		const href = compareHref(7, 12, 42);
		const url = new URL(href, 'http://app.test');

		expect(href).toBe('/compare?before=7&after=12#node-42');
		expect(parseCompareParams(url.searchParams)).toEqual({ before: 7, after: 12 });
		expect(parseNodeHash(url.hash)).toBe(42);
	});
});

describe('node anchors', () => {
	it('round-trips a node id through the hash', () => {
		expect(nodeAnchorId(42)).toBe('node-42');
		expect(parseNodeHash(`#${nodeAnchorId(42)}`)).toBe(42);
	});

	it('ignores any other hash', () => {
		for (const hash of ['', '#', '#node-', '#node-0', '#node-4a', '#clause-4', 'node-4']) {
			expect(parseNodeHash(hash)).toBeNull();
		}
	});
});
