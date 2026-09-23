import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';

import fixture from '$lib/fixtures/result.json';
import { visibleFindings } from '$lib/result/derive';
import type { JobResult } from '$lib/result/types';

import ChangesView from './ChangesView.svelte';

// JSON imports type enum values as plain strings; src/lib/fixtures/result.spec.ts checks them.
const result = fixture as JobResult;
const loss = result.findings['C-011'];

describe('ChangesView on the demo fixture', () => {
	it('shows the summary and every block of the comparison', async () => {
		const screen = render(ChangesView, { result });

		await expect.element(screen.getByRole('heading', { name: 'Сводка изменений' })).toBeVisible();
		for (const block of result.blocks) {
			await expect.element(screen.getByRole('heading', { name: block.title })).toBeVisible();
		}
	});

	it('opens a finding from the conclusion, counts its verdict and closes from a quote', async () => {
		const screen = render(ChangesView, { result });
		const total = visibleFindings(result).length;

		await screen.getByRole('button', { name: 'C-011', exact: true }).click();
		const dialog = screen.getByRole('dialog');
		await expect.element(dialog).toBeVisible();
		await expect
			.element(dialog.getByRole('heading', { name: loss.evidence.conclusion }))
			.toBeVisible();

		await dialog.getByRole('button', { name: '✓ Подтвердить' }).click();
		await expect
			.element(screen.getByText(`Проверено сотрудником: 1 из ${total}`))
			.toBeInTheDocument();

		await dialog
			.getByRole('button', { name: /^Документ «/ })
			.first()
			.click();
		expect((screen.container.querySelector('dialog') as HTMLDialogElement).open).toBe(false);
	});
});
