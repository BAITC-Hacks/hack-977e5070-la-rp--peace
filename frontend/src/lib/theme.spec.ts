import { describe, expect, it } from 'vitest';

import { THEME_STORAGE_KEY, applyTheme, readTheme, saveTheme, type ThemeStorage } from './theme';

function memoryStorage(initial: Record<string, string> = {}): ThemeStorage & {
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

const blockedStorage: ThemeStorage = {
	getItem: () => {
		throw new DOMException('blocked', 'SecurityError');
	},
	setItem: () => {
		throw new DOMException('blocked', 'SecurityError');
	},
	removeItem: () => {
		throw new DOMException('blocked', 'SecurityError');
	}
};

describe('readTheme', () => {
	it('returns a saved light or dark choice', () => {
		expect(readTheme(memoryStorage({ [THEME_STORAGE_KEY]: 'dark' }))).toBe('dark');
		expect(readTheme(memoryStorage({ [THEME_STORAGE_KEY]: 'light' }))).toBe('light');
	});

	it('falls back to the system theme for missing, unknown or unreadable values', () => {
		expect(readTheme(memoryStorage())).toBe('system');
		expect(readTheme(memoryStorage({ [THEME_STORAGE_KEY]: 'sepia' }))).toBe('system');
		expect(readTheme(null)).toBe('system');
		expect(readTheme(blockedStorage)).toBe('system');
	});
});

describe('saveTheme', () => {
	it('stores light and dark, and clears the entry for the system theme', () => {
		const storage = memoryStorage();
		saveTheme(storage, 'dark');
		expect(storage.entries.get(THEME_STORAGE_KEY)).toBe('dark');
		saveTheme(storage, 'system');
		expect(storage.entries.has(THEME_STORAGE_KEY)).toBe(false);
	});

	it('does not throw when storage is blocked or missing', () => {
		expect(() => saveTheme(blockedStorage, 'light')).not.toThrow();
		expect(() => saveTheme(null, 'light')).not.toThrow();
	});
});

describe('applyTheme', () => {
	it('sets data-theme for an explicit choice and removes it for the system theme', () => {
		const root = { dataset: {} as DOMStringMap };
		applyTheme(root, 'light');
		expect(root.dataset.theme).toBe('light');
		applyTheme(root, 'system');
		expect(root.dataset).not.toHaveProperty('theme');
	});
});
