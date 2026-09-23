import { describe, expect, it } from 'vitest';

import { FINDING_TYPES, TYPE_LABELS, formatScore } from './labels';

describe('FINDING_TYPES', () => {
	it('lists every labelled type once', () => {
		expect(new Set(FINDING_TYPES).size).toBe(FINDING_TYPES.length);
		expect([...FINDING_TYPES].sort()).toEqual(Object.keys(TYPE_LABELS).sort());
	});
});

describe('formatScore', () => {
	it('prints two decimals with a Russian decimal comma', () => {
		expect(formatScore(0.75)).toBe('0,75');
		expect(formatScore(0.4)).toBe('0,40');
		expect(formatScore(1)).toBe('1,00');
	});
});
