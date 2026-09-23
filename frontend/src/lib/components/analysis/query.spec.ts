import { describe, expect, it } from 'vitest';

import { tabFromQuery, tabQuery } from './query';

describe('tabFromQuery', () => {
	it('reads the sub-page from ?tab=', () => {
		expect(tabFromQuery(new URLSearchParams('tab=overlap'))).toBe('overlap');
		expect(tabFromQuery(new URLSearchParams('tab=conflict'))).toBe('conflict');
	});

	it('opens «Потеря функций» without a tab or with an unknown one', () => {
		expect(tabFromQuery(new URLSearchParams(''))).toBe('loss');
		expect(tabFromQuery(new URLSearchParams('tab=chat'))).toBe('loss');
	});
});

describe('tabQuery', () => {
	it('sets the tab and keeps the other parameters', () => {
		expect(tabQuery(new URLSearchParams('tab=loss&x=1'), 'duplication')).toBe(
			'?tab=duplication&x=1'
		);
		expect(tabQuery(new URLSearchParams(''), 'overlap')).toBe('?tab=overlap');
	});
});
