import { describe, expect, it } from 'vitest';

import { ReviewState } from './review.svelte';
import type { Finding, Verdict } from './types';

function finding(id: string, review: Verdict | null = null): Finding {
	return {
		id,
		type: 'loss',
		block: 'ИБ и режим',
		title: 'Потеря функции',
		from: ['f_mob'],
		to: [],
		evidence: {
			conclusion: 'Функция не закреплена',
			method: 'Поиск по смыслу',
			steps: [],
			confidence: 'high'
		},
		review
	};
}

describe('ReviewState', () => {
	it('starts from the verdicts the result carries', () => {
		const review = new ReviewState([finding('C-001', 'ok'), finding('C-002'), finding('C-003')]);

		expect(review.total).toBe(3);
		expect(review.reviewed).toBe(1);
		expect(review.verdictOf('C-001')).toBe('ok');
		expect(review.verdictOf('C-002')).toBeNull();
	});

	it('sets a verdict and counts the finding as reviewed', () => {
		const review = new ReviewState([finding('C-001'), finding('C-002')]);

		expect(review.toggle('C-002', 'no')).toBe('no');

		expect(review.verdictOf('C-002')).toBe('no');
		expect(review.reviewed).toBe(1);
	});

	it('clears the verdict on a second click of the same button', () => {
		const review = new ReviewState([finding('C-001')]);
		review.toggle('C-001', 'ok');

		expect(review.toggle('C-001', 'ok')).toBeNull();

		expect(review.verdictOf('C-001')).toBeNull();
		expect(review.reviewed).toBe(0);
	});

	it('switches between confirm and reject', () => {
		const review = new ReviewState([finding('C-001', 'ok')]);

		expect(review.toggle('C-001', 'no')).toBe('no');

		expect(review.verdictOf('C-001')).toBe('no');
		expect(review.reviewed).toBe(1);
	});

	it('ignores findings it was not given', () => {
		const review = new ReviewState([finding('C-001')]);

		expect(review.toggle('C-404', 'ok')).toBeNull();

		expect(review.verdictOf('C-404')).toBeNull();
		expect(review.reviewed).toBe(0);
	});
});
