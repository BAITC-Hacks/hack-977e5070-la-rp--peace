import { beforeEach, describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';

import { THEME_STORAGE_KEY } from '$lib/theme';

import ThemeToggle from './ThemeToggle.svelte';

describe('ThemeToggle', () => {
	beforeEach(() => {
		localStorage.clear();
		delete document.documentElement.dataset.theme;
	});

	it('starts from the saved choice', async () => {
		localStorage.setItem(THEME_STORAGE_KEY, 'dark');
		const screen = render(ThemeToggle);

		await expect
			.element(screen.getByRole('button', { name: 'Тёмная' }))
			.toHaveAttribute('aria-pressed', 'true');
	});

	it('applies and remembers a picked theme, and forgets it when back to the system one', async () => {
		const screen = render(ThemeToggle);

		await screen.getByRole('button', { name: 'Светлая' }).click();
		await expect
			.element(screen.getByRole('button', { name: 'Светлая' }))
			.toHaveAttribute('aria-pressed', 'true');
		expect(document.documentElement.dataset.theme).toBe('light');
		expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');

		await screen.getByRole('button', { name: 'Системная' }).click();
		await expect
			.element(screen.getByRole('button', { name: 'Системная' }))
			.toHaveAttribute('aria-pressed', 'true');
		expect(document.documentElement.dataset).not.toHaveProperty('theme');
		expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
	});
});
