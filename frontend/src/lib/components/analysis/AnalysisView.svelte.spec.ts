import { describe, expect, it, vi } from 'vitest';
import { userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';

import fixture from '$lib/fixtures/result.json';
import { visibleFindings } from '$lib/result/derive';
import { ReviewState } from '$lib/result/review.svelte';
import type { Finding, JobResult, Source } from '$lib/result/types';

import AnalysisView from './AnalysisView.svelte';

import '../../../routes/layout.css';

// JSON imports type enum values as plain strings; src/lib/fixtures/result.spec.ts checks them.
const demo = fixture as JobResult;

const quote: Source = {
	doc: 'after',
	block: 'Положение Управления IT',
	node_id: 22,
	clause: 'п. 4.6',
	quote: 'утверждает порядок внедрения изменений информационных систем',
	item: 'k_ord'
};

// The fixture has no contradiction; this one claims a high confidence that must be shown as medium.
const contradiction: Finding = {
	id: 'C-015',
	type: 'contradiction',
	block: 'IT и цифровизация',
	title: 'Противоречие функций',
	desc: 'Порядок внедрения изменений ИС утверждают два подразделения',
	from: [],
	to: ['k_ord'],
	evidence: {
		conclusion: 'Порядок внедрения изменений ИС утверждают и Управление IT, и ЦЦТ.',
		method: 'Сравнение функций разных субъектов над одним объектом.',
		steps: [{ kind: 'fact', text: 'Управление IT утверждает порядок.', sources: [quote] }],
		confidence: 'high',
		confidence_note: 'Факты подтверждены цитатами.'
	},
	review: null
};

// No quote: must be neither shown nor counted (I1).
const unsourced: Finding = {
	...contradiction,
	id: 'C-016',
	evidence: { ...contradiction.evidence, steps: [] }
};

function withFindings(extra: Finding[], without: string[] = []): JobResult {
	const findings = Object.fromEntries(
		Object.entries(demo.findings).filter(([id]) => !without.includes(id))
	);
	for (const finding of extra) {
		findings[finding.id] = finding;
	}
	return { ...demo, findings };
}

function setup(result: JobResult = demo, tab?: 'loss' | 'duplication' | 'conflict' | 'overlap') {
	const review = new ReviewState(visibleFindings(result));
	const onquote = vi.fn();
	const screen = render(AnalysisView, { result, review, onquote, ...(tab ? { tab } : {}) });
	return { screen, review, onquote };
}

describe('AnalysisView', () => {
	it('shows the four sub-pages with their counts and opens «Потеря функций» first', async () => {
		const { screen } = setup();

		const tabs = screen.getByRole('tab');
		await expect.element(tabs.nth(0)).toHaveTextContent(/^Потеря функций 1$/);
		await expect.element(tabs.nth(1)).toHaveTextContent(/^Дублирование 1$/);
		await expect.element(tabs.nth(2)).toHaveTextContent(/^Конфликт интересов 1$/);
		await expect.element(tabs.nth(3)).toHaveTextContent(/^Пересечение зон 1$/);
		await expect.element(tabs.nth(0)).toHaveAttribute('aria-selected', 'true');

		const panel = screen.getByRole('tabpanel');
		await expect.element(panel).toHaveAccessibleName(/Потеря функций/);
		await expect.element(panel.getByRole('button', { name: /C-011/ })).toBeVisible();
		expect(panel.getByRole('button').elements()).toHaveLength(1);
	});

	it('sorts every problem finding of the demo into its sub-page and leaves the rest out', async () => {
		const { screen } = setup();
		const expected = {
			'Потеря функций': 'C-011',
			Дублирование: 'C-013',
			'Конфликт интересов': 'C-010',
			'Пересечение зон': 'C-014'
		};

		for (const [label, id] of Object.entries(expected)) {
			await screen.getByRole('tab', { name: new RegExp(label) }).click();
			const panel = screen.getByRole('tabpanel');
			await expect.element(panel.getByRole('button', { name: new RegExp(id) })).toBeVisible();
			expect(panel.getByRole('button').elements()).toHaveLength(1);
		}
		expect(screen.container.textContent).not.toContain('C-004');
	});

	it('moves between sub-pages with the arrows, Home and End', async () => {
		const { screen } = setup();
		const tabs = screen.getByRole('tab');
		await tabs.nth(0).click();

		await userEvent.keyboard('{ArrowRight}');
		await expect.element(tabs.nth(1)).toHaveFocus();
		await expect.element(tabs.nth(1)).toHaveAttribute('aria-selected', 'true');
		await expect.element(tabs.nth(0)).toHaveAttribute('aria-selected', 'false');
		await expect.element(tabs.nth(0)).toHaveAttribute('tabindex', '-1');

		await userEvent.keyboard('{End}');
		await expect.element(tabs.nth(3)).toHaveFocus();
		await expect.element(screen.getByRole('tabpanel')).toHaveAccessibleName(/Пересечение зон/);

		await userEvent.keyboard('{ArrowRight}');
		await expect.element(tabs.nth(0)).toHaveFocus();

		await userEvent.keyboard('{ArrowLeft}');
		await expect.element(tabs.nth(3)).toHaveFocus();

		await userEvent.keyboard('{Home}');
		await expect.element(tabs.nth(0)).toHaveFocus();
		await expect.element(tabs.nth(0)).toHaveAttribute('aria-selected', 'true');
	});

	it('opens the sub-page it is given', async () => {
		const { screen } = setup(demo, 'overlap');

		await expect
			.element(screen.getByRole('tab', { name: /Пересечение зон/ }))
			.toHaveAttribute('aria-selected', 'true');
		await expect
			.element(screen.getByRole('tabpanel').getByRole('button', { name: /C-014/ }))
			.toBeVisible();
	});

	it('shows a card with type, block, description and confidence with its basis', async () => {
		const { screen } = setup(demo, 'overlap');

		const card = screen.getByRole('button', { name: /C-014/ });
		await expect.element(card).toHaveTextContent('Пересечение зон');
		await expect.element(card).toHaveTextContent('IT и цифровизация');
		await expect.element(card).toHaveTextContent(demo.findings['C-014'].desc ?? '');
		await expect.element(card).toHaveTextContent(/Уверенность:\s*средняя\s*— Факты подтверждены/);
	});

	it('says so on a sub-page without findings', async () => {
		const { screen } = setup(withFindings([], ['C-013']), 'duplication');

		await expect
			.element(screen.getByRole('tab', { name: /Дублирование/ }))
			.toHaveTextContent(/^Дублирование 0$/);
		await expect.element(screen.getByRole('tabpanel')).toHaveTextContent('Дублирований не найдено');
	});

	it('labels conflicts and contradictions apart and caps the contradiction at medium', async () => {
		const { screen } = setup(withFindings([contradiction, unsourced]), 'conflict');

		await expect
			.element(screen.getByRole('tab', { name: /Конфликт интересов/ }))
			.toHaveTextContent(/^Конфликт интересов 2$/);
		const panel = screen.getByRole('tabpanel');
		const conflictCard = panel.getByRole('button', { name: /C-010/ });
		const contradictionCard = panel.getByRole('button', { name: /C-015/ });
		await expect.element(conflictCard).toHaveTextContent(/^Конфликт интересов/);
		await expect.element(conflictCard).toHaveTextContent(/Уверенность:\s*высокая/);
		await expect.element(contradictionCard).toHaveTextContent(/^Противоречие функций/);
		await expect.element(contradictionCard).toHaveTextContent(/Уверенность:\s*средняя/);
		expect(screen.container.textContent).not.toContain('C-016');

		await contradictionCard.click();
		const dialog = screen.getByRole('dialog');
		await expect.element(dialog).toBeVisible();
		await expect.element(dialog.getByText('средняя', { exact: true })).toBeVisible();
		expect(dialog.element().textContent).not.toContain('высокая');
	});

	it('opens the evidence with Enter and shows the verdict on the card after closing', async () => {
		const { screen, review } = setup();
		const card = screen.getByRole('button', { name: /C-011/ });

		(card.element() as HTMLElement).focus();
		await userEvent.keyboard('{Enter}');
		const dialog = screen.getByRole('dialog');
		await expect.element(dialog).toBeVisible();
		await expect
			.element(dialog.getByRole('heading', { level: 2 }))
			.toHaveTextContent(demo.findings['C-011'].evidence.conclusion);

		await dialog.getByRole('button', { name: '✓ Подтвердить' }).click();
		await dialog.getByRole('button', { name: 'Закрыть' }).click();

		await vi.waitFor(() => expect(screen.container.querySelector('dialog')?.open).toBe(false));
		expect(review.verdictOf('C-011')).toBe('ok');
		await expect.element(card).toHaveTextContent('✓ подтверждено');
	});

	it('closes the evidence and hands a clicked quote to onquote', async () => {
		const { screen, onquote } = setup(demo, 'duplication');

		await screen.getByRole('button', { name: /C-013/ }).click();
		await screen
			.getByRole('dialog')
			.getByRole('button', { name: /Положение Управления IT · п. 4.2/ })
			.click();

		expect(onquote).toHaveBeenCalledWith(demo.findings['C-013'].evidence.steps[0].sources[0]);
		await vi.waitFor(() => expect(screen.container.querySelector('dialog')?.open).toBe(false));
	});
});
