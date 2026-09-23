import { describe, expect, it } from 'vitest';

import { nodeAnchorId, parseCompareParams, parseNodeHash } from './anchor';

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
