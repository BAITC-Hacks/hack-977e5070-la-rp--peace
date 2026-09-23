import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';

import fixture from '$lib/fixtures/result.json';
import { DISCLAIMER } from '$lib/result/labels';
import type { JobResult } from '$lib/result/types';
import type { ReviewStorage, SavedVerdicts } from '$lib/review/storage';

import ResultsShellHarness from './ResultsShellHarness.svelte';

import '../../../routes/layout.css';

// JSON imports type enum values as plain strings; src/lib/fixtures/result.spec.ts checks them.
const result = fixture as JobResult;

function memoryStorage(): ReviewStorage & { saved: Map<string, SavedVerdicts> } {
	const saved = new Map<string, SavedVerdicts>();
	return {
		saved,
		load: (jobId) => ({ ...saved.get(jobId) }),
		save: (jobId, verdicts) => void saved.set(jobId, { ...verdicts })
	};
}

describe('ResultsShell', () => {
	it.each([['changes'], ['analysis']] as const)(
		'shows the menu and the disclaimer on «%s» (I6)',
		async (section) => {
			const screen = render(ResultsShellHarness, {
				result,
				storage: memoryStorage(),
				pages: [section]
			});

			await expect.element(screen.getByRole('note')).toHaveTextContent(DISCLAIMER);
			await expect
				.element(screen.getByRole('navigation', { name: 'Разделы результата' }))
				.toBeVisible();
		}
	);

	it('shares one set of marks between «Изменения» and «Анализ», saved under the job id', async () => {
		const storage = memoryStorage();
		const screen = render(ResultsShellHarness, {
			result,
			storage,
			pages: ['changes', 'analysis']
		});
		const analysis = screen.container.querySelector('[data-page="analysis"]') as HTMLElement;

		await screen.getByRole('button', { name: 'C-011', exact: true }).click();
		// Only the evidence panel of «Изменения» is open; the one of «Анализ» stays closed.
		await screen.getByRole('dialog').getByRole('button', { name: '✓ Подтвердить' }).click();

		await vi.waitFor(() => expect(analysis.textContent).toContain('✓ подтверждено'));
		expect(storage.saved.get(result.job_id)).toEqual({ 'C-011': 'ok' });
	});

	it('starts from the marks saved for the job', async () => {
		const storage = memoryStorage();
		storage.save(result.job_id, { 'C-011': 'no' });
		const screen = render(ResultsShellHarness, { result, storage, pages: ['analysis'] });

		await expect
			.element(screen.getByRole('button', { name: /C-011/ }))
			.toHaveTextContent('✕ отклонено');
	});
});
