import { afterEach, describe, expect, it, vi } from 'vitest';

import { localReviewStorage, reviewStorageKey, webReviewStorage, type WebStorage } from './storage';

function memoryStorage(initial: Record<string, string> = {}): WebStorage & {
	entries: Map<string, string>;
} {
	const entries = new Map(Object.entries(initial));
	return {
		entries,
		getItem: (key) => entries.get(key) ?? null,
		setItem: (key, value) => void entries.set(key, value),
		removeItem: (key) => void entries.delete(key)
	};
}

function blocked(): never {
	throw new DOMException('blocked', 'SecurityError');
}

const blockedStorage: WebStorage = {
	getItem: blocked,
	setItem: blocked,
	removeItem: blocked
};

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('reviewStorageKey', () => {
	it('keeps the marks of each analysis under its own key', () => {
		expect(reviewStorageKey('job-1')).toBe('larp:review:job-1');
	});
});

describe('webReviewStorage', () => {
	it('reads back what it saved, per analysis', () => {
		const memory = memoryStorage();
		const storage = webReviewStorage(() => memory);

		storage.save('job-1', { 'C-001': 'ok', 'C-002': null });
		storage.save('job-2', { 'C-001': 'no' });

		expect(storage.load('job-1')).toEqual({ 'C-001': 'ok', 'C-002': null });
		expect(storage.load('job-2')).toEqual({ 'C-001': 'no' });
		expect(storage.load('job-3')).toEqual({});
	});

	it('removes the key once no marks are left', () => {
		const memory = memoryStorage();
		const storage = webReviewStorage(() => memory);
		storage.save('job-1', { 'C-001': 'ok' });

		storage.save('job-1', {});

		expect(memory.entries.has(reviewStorageKey('job-1'))).toBe(false);
	});

	it('ignores damaged or foreign data under the key', () => {
		const key = reviewStorageKey('job-1');

		expect(webReviewStorage(() => memoryStorage({ [key]: '{not json' })).load('job-1')).toEqual({});
		expect(webReviewStorage(() => memoryStorage({ [key]: '["ok"]' })).load('job-1')).toEqual({});
		expect(webReviewStorage(() => memoryStorage({ [key]: '"ok"' })).load('job-1')).toEqual({});
		expect(
			webReviewStorage(() =>
				memoryStorage({ [key]: '{"C-001":"ok","C-002":"maybe","C-003":1,"C-004":null}' })
			).load('job-1')
		).toEqual({ 'C-001': 'ok', 'C-004': null });
	});

	it('does not throw where the browser blocks storage', () => {
		const refusing = webReviewStorage(() => blockedStorage);
		const missing = webReviewStorage(blocked);

		for (const storage of [refusing, missing]) {
			expect(storage.load('job-1')).toEqual({});
			expect(() => storage.save('job-1', { 'C-001': 'ok' })).not.toThrow();
			expect(() => storage.save('job-1', {})).not.toThrow();
		}
	});
});

describe('localReviewStorage', () => {
	it('keeps the marks in localStorage', () => {
		const memory = memoryStorage();
		vi.stubGlobal('window', { localStorage: memory });

		localReviewStorage.save('job-1', { 'C-011': 'no' });

		expect(memory.entries.get('larp:review:job-1')).toBe('{"C-011":"no"}');
		expect(localReviewStorage.load('job-1')).toEqual({ 'C-011': 'no' });
	});

	it('does not throw where there is no localStorage at all', () => {
		vi.stubGlobal('window', undefined);

		expect(localReviewStorage.load('job-1')).toEqual({});
		expect(() => localReviewStorage.save('job-1', { 'C-011': 'no' })).not.toThrow();
	});
});
