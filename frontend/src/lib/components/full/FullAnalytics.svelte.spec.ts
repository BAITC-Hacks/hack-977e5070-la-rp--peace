import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';

import fixture from '$lib/fixtures/result.json';
import { visibleFindings } from '$lib/result/derive';
import { CONFIDENCE_LABELS, TYPE_LABELS } from '$lib/result/labels';
import { ReviewState } from '$lib/result/review.svelte';
import type { Finding, JobResult } from '$lib/result/types';

import FullAnalytics from './FullAnalytics.svelte';

import '../../../routes/layout.css';

// JSON imports type enum values as plain strings; src/lib/fixtures/result.spec.ts checks them.
const result = fixture as JobResult;
const sourced = visibleFindings(result);
const loss = result.findings['C-011'];
/** A copy of the loss with its quotes dropped: it must not be listed (I1). */
const unsourced: Finding = {
	...loss,
	id: 'C-099',
	evidence: {
		...loss.evidence,
		steps: loss.evidence.steps.map((step) => ({ ...step, sources: [] }))
	}
};

async function show() {
	const review = new ReviewState(sourced);
	const onopen = vi.fn();
	const screen = await render(FullAnalytics, {
		findings: [...sourced, unsourced],
		review,
		onopen
	});
	await screen.getByText('Показать полную аналитику').click();
	return { screen, review, onopen };
}

describe('FullAnalytics on the demo fixture', () => {
	it('is collapsed until «Показать полную аналитику» is clicked', async () => {
		const screen = await render(FullAnalytics, {
			findings: sourced,
			review: new ReviewState(sourced),
			onopen: vi.fn()
		});
		// A closed <details> keeps its content out of the accessibility tree.
		const list = screen.getByRole('list', { name: 'Выводы', includeHidden: true });
		await expect.element(list).toBeInTheDocument();
		await expect.element(list).not.toBeVisible();

		await screen.getByText('Показать полную аналитику').click();

		await expect.element(list).toBeVisible();
	});

	it('lists every sourced finding of the page, in its order', async () => {
		const { screen } = await show();

		const items = screen.getByRole('listitem');
		await expect.element(items.first()).toBeVisible();
		expect(items.elements()).toHaveLength(sourced.length);
		expect(items.elements().map((item) => item.textContent)).toEqual(
			sourced.map((finding) => expect.stringContaining(`· ${finding.id}`))
		);
		expect(screen.getByText('C-099').elements()).toHaveLength(0);
	});

	it('shows type, title, conclusion, confidence and the employee mark of a finding', async () => {
		const { screen } = await show();

		const item = screen.getByRole('listitem').filter({ hasText: `· ${loss.id}` });
		await expect.element(item).toHaveTextContent(`${TYPE_LABELS[loss.type]} · ${loss.id}`);
		await expect.element(item).toHaveTextContent(loss.title);
		await expect.element(item).toHaveTextContent(loss.evidence.conclusion);
		await expect
			.element(item)
			.toHaveTextContent(`Уверенность: ${CONFIDENCE_LABELS[loss.evidence.confidence]}`);
		await expect.element(item).toHaveTextContent('не проверено');
	});

	it('follows the marks the employee sets', async () => {
		const { screen, review } = await show();
		const item = screen.getByRole('listitem').filter({ hasText: `· ${loss.id}` });

		review.toggle(loss.id, 'no');
		await expect.element(item.getByText('✕ отклонено')).toBeVisible();

		review.toggle(loss.id, 'ok');
		await expect.element(item.getByText('✓ подтверждено')).toBeVisible();
	});

	it('opens a finding with «Открыть»', async () => {
		const { screen, onopen } = await show();

		await screen.getByRole('button', { name: `Открыть ${loss.id}` }).click();

		expect(onopen).toHaveBeenCalledExactlyOnceWith(loss.id);
	});

	it('says so when the page has no sourced findings', async () => {
		const screen = await render(FullAnalytics, {
			findings: [unsourced],
			review: new ReviewState([]),
			onopen: vi.fn()
		});

		await screen.getByText('Показать полную аналитику').click();

		await expect.element(screen.getByText('Выводов на этой странице нет.')).toBeVisible();
		expect(screen.getByRole('listitem').elements()).toHaveLength(0);
	});
});
