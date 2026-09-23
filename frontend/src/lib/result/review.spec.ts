import { describe, expect, it } from 'vitest';

import { reviewStorageKey, webReviewStorage, type WebStorage } from '$lib/review/storage';

import { ReviewState } from './review.svelte';
import type { Finding, Verdict } from './types';

/** A `localStorage` stand-in: the marks go through the real JSON storage code. */
function memoryStorage(): WebStorage & { entries: Map<string, string> } {
	const entries = new Map<string, string>();
	return {
		entries,
		getItem: (key) => entries.get(key) ?? null,
		setItem: (key, value) => void entries.set(key, value),
		removeItem: (key) => void entries.delete(key)
	};
}

function saved(memory: ReturnType<typeof memoryStorage>, jobId = 'job-1'): unknown {
	const raw = memory.entries.get(reviewStorageKey(jobId));
	return raw === undefined ? undefined : JSON.parse(raw);
}

function blocked(): never {
	throw new DOMException('blocked', 'SecurityError');
}

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

describe('ReviewState with a storage', () => {
	it('keeps a mark when the page is opened again', () => {
		const memory = memoryStorage();
		const storage = webReviewStorage(() => memory);
		const findings = [finding('C-001'), finding('C-002')];
		new ReviewState(findings, { jobId: 'job-1', storage }).toggle('C-002', 'no');

		const reopened = new ReviewState(findings, { jobId: 'job-1', storage });

		expect(reopened.verdictOf('C-002')).toBe('no');
		expect(reopened.reviewed).toBe(1);
		expect(new ReviewState(findings, { jobId: 'job-2', storage }).reviewed).toBe(0);
	});

	it('puts the saved marks on top of the verdicts the result carries', () => {
		const memory = memoryStorage();
		const storage = webReviewStorage(() => memory);
		storage.save('job-1', { 'C-001': 'no', 'C-003': 'ok' });

		const findings = [finding('C-001', 'ok'), finding('C-002', 'ok'), finding('C-003')];

		const review = new ReviewState(findings, { jobId: 'job-1', storage });

		expect(review.verdictOf('C-001')).toBe('no');
		expect(review.verdictOf('C-002')).toBe('ok');
		expect(review.verdictOf('C-003')).toBe('ok');
	});

	it('removes a mark from the storage when it is taken back', () => {
		const memory = memoryStorage();
		const storage = webReviewStorage(() => memory);
		const review = new ReviewState([finding('C-001'), finding('C-002')], {
			jobId: 'job-1',
			storage
		});
		review.toggle('C-001', 'ok');
		review.toggle('C-002', 'no');

		review.toggle('C-001', 'ok');

		expect(saved(memory)).toEqual({ 'C-002': 'no' });
		review.toggle('C-002', 'no');
		expect(saved(memory)).toBeUndefined();
	});

	it('remembers that a verdict the result carries was taken back', () => {
		const memory = memoryStorage();
		const storage = webReviewStorage(() => memory);
		const findings = [finding('C-001', 'ok')];
		const review = new ReviewState(findings, { jobId: 'job-1', storage });

		review.toggle('C-001', 'ok');
		expect(new ReviewState(findings, { jobId: 'job-1', storage }).verdictOf('C-001')).toBeNull();

		review.toggle('C-001', 'ok');
		expect(saved(memory)).toBeUndefined();
		expect(new ReviewState(findings, { jobId: 'job-1', storage }).verdictOf('C-001')).toBe('ok');
	});

	it('keeps the saved marks of findings it was not given', () => {
		const memory = memoryStorage();
		const storage = webReviewStorage(() => memory);
		storage.save('job-1', { 'C-099': 'ok' });
		const review = new ReviewState([finding('C-001')], { jobId: 'job-1', storage });

		review.toggle('C-001', 'no');

		expect(review.verdictOf('C-099')).toBeNull();
		expect(review.reviewed).toBe(1);
		expect(saved(memory)).toEqual({ 'C-001': 'no', 'C-099': 'ok' });
	});

	it('still takes marks when the storage throws', () => {
		const refusing: WebStorage = { getItem: blocked, setItem: blocked, removeItem: blocked };

		for (const storage of [webReviewStorage(() => refusing), webReviewStorage(blocked)]) {
			const review = new ReviewState([finding('C-001', 'ok'), finding('C-002')], {
				jobId: 'job-1',
				storage
			});

			expect(review.verdictOf('C-001')).toBe('ok');
			expect(review.toggle('C-002', 'no')).toBe('no');
			expect(review.toggle('C-001', 'ok')).toBeNull();
			expect(review.verdictOf('C-002')).toBe('no');
			expect(review.reviewed).toBe(1);
		}
	});
});
