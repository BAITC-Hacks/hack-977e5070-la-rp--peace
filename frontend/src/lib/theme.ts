/** Colour theme picked by the user; `system` follows `prefers-color-scheme` (src/routes/layout.css). */
export type ThemeChoice = 'system' | 'light' | 'dark';

/** Choices in the order the switcher shows them. */
export const THEME_CHOICES: readonly ThemeChoice[] = ['system', 'light', 'dark'];

export const THEME_LABELS: Record<ThemeChoice, string> = {
	system: 'Системная',
	light: 'Светлая',
	dark: 'Тёмная'
};

/** localStorage key; src/app.html reads it as well, to apply the theme before the first paint. */
export const THEME_STORAGE_KEY = 'theme';

/** The part of `Storage` the theme uses, so tests can pass a plain object. */
export type ThemeStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

/** `localStorage`, or null where the browser blocks it (disabled site data, some private modes). */
export function browserStorage(): ThemeStorage | null {
	try {
		return window.localStorage;
	} catch {
		return null;
	}
}

/** The saved choice; anything unreadable or unknown means `system`. */
export function readTheme(storage: ThemeStorage | null): ThemeChoice {
	try {
		const value = storage?.getItem(THEME_STORAGE_KEY);
		return value === 'light' || value === 'dark' ? value : 'system';
	} catch {
		return 'system';
	}
}

/** Remembers the choice; `system` is stored as no entry at all. */
export function saveTheme(storage: ThemeStorage | null, choice: ThemeChoice): void {
	try {
		if (choice === 'system') {
			storage?.removeItem(THEME_STORAGE_KEY);
		} else {
			storage?.setItem(THEME_STORAGE_KEY, choice);
		}
	} catch {
		// Storage refused the write: the theme still applies to the open page, it just is not remembered.
	}
}

/** Sets `data-theme` on the root element, or removes it so that the system setting applies. */
export function applyTheme(root: Pick<HTMLElement, 'dataset'>, choice: ThemeChoice): void {
	if (choice === 'system') {
		delete root.dataset.theme;
	} else {
		root.dataset.theme = choice;
	}
}
