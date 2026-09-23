import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';

import { DISCLAIMER } from '$lib/result/labels';

import ResultsHeader from './ResultsHeader.svelte';

describe('ResultsHeader', () => {
	it('links «Изменения» and «Анализ» of the analysis and marks the current one', async () => {
		const screen = render(ResultsHeader, { id: 'demo', current: 'analysis' });
		const menu = screen.getByRole('navigation', { name: 'Разделы результата' });

		const changes = menu.getByRole('link', { name: 'Изменения' });
		const analysis = menu.getByRole('link', { name: 'Анализ' });
		await expect.element(changes).toHaveAttribute('href', '/analyses/demo/changes');
		await expect.element(analysis).toHaveAttribute('href', '/analyses/demo/analysis');
		await expect.element(analysis).toHaveAttribute('aria-current', 'page');
		await expect.element(changes).not.toHaveAttribute('aria-current');
	});

	it('shows «Чат» as inactive, without a page to go to', async () => {
		const screen = render(ResultsHeader, { id: 'demo', current: 'changes' });

		const chat = screen.getByRole('link', { name: 'Чат' });
		await expect.element(chat).toHaveAttribute('aria-disabled', 'true');
		expect(chat.element().hasAttribute('href')).toBe(false);
		await expect
			.element(screen.getByRole('link', { name: 'Изменения' }))
			.toHaveAttribute('aria-current', 'page');
	});

	it('shows the disclaimer (I6)', async () => {
		const screen = render(ResultsHeader, { id: 'demo', current: null });

		await expect.element(screen.getByRole('note')).toHaveTextContent(DISCLAIMER);
		expect(screen.container.querySelector('[aria-current]')).toBeNull();
	});
});
