import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';

import type { DocumentCardValues } from '$lib/api/document';

import DocumentCard from './DocumentCard.svelte';

const quote = (text: string, start = 0) => ({ text, start, end: start + text.length });

const EVIDENCE: Record<string, unknown> = {
	title: {
		status: 'extracted',
		value: 'Положение о внутреннем аудите АО «Компания»',
		quotes: [quote('ПОЛОЖЕНИЕ О ВНУТРЕННЕМ АУДИТЕ АО «Компания»', 40)]
	},
	organization: {
		status: 'ambiguous',
		value: 'АО «Компания»',
		quotes: [],
		reason: 'цитата не найдена в тексте: «АО Компания»'
	},
	approved_on: {
		status: 'extracted',
		value: '2022-12-23',
		quotes: [quote('от «23» декабря 2022 года', 10)]
	},
	effective_from: {
		status: 'not_found',
		value: null,
		quotes: [],
		reason: 'календарная дата не указана'
	},
	extra: [
		{
			name: 'Условие вступления в силу',
			value: 'с даты утверждения',
			quotes: [quote('вступает в силу с даты утверждения', 500)]
		}
	]
};

const EMPTY_CARD: DocumentCardValues = {
	title: null,
	document_type: null,
	organization: null,
	revision: null,
	approved_by: null,
	approval_document_type: null,
	approval_number: null,
	document_created_on: null,
	approved_on: null,
	effective_from: null
};

const CARD: DocumentCardValues = {
	...EMPTY_CARD,
	title: 'Положение о внутреннем аудите АО «Компания»',
	approved_on: '2022-12-23'
};

function row(container: HTMLElement, name: string): HTMLElement {
	const element = container.querySelector<HTMLElement>(`[data-field="${name}"]`);
	if (element === null) {
		throw new Error(`no row ${name}`);
	}
	return element;
}

describe('DocumentCard', () => {
	it('shows accepted values with the quotes that support them', async () => {
		const screen = await render(DocumentCard, { card: CARD, evidence: EVIDENCE });

		await expect.element(screen.getByText('Дата утверждения')).toBeVisible();
		expect(row(screen.container, 'approved_on').textContent).toContain('23.12.2022');
		await expect.element(screen.getByText('«от «23» декабря 2022 года»')).toBeVisible();
		await expect
			.element(screen.getByText('«ПОЛОЖЕНИЕ О ВНУТРЕННЕМ АУДИТЕ АО «Компания»»'))
			.toBeVisible();
	});

	it('says «не найдено» with the reason', async () => {
		const screen = await render(DocumentCard, { card: CARD, evidence: EVIDENCE });

		expect(row(screen.container, 'effective_from').textContent?.trim()).toBe(
			'не найдено — календарная дата не указана'
		);
	});

	it('marks an unconfirmed value as a warning', async () => {
		const screen = await render(DocumentCard, { card: CARD, evidence: EVIDENCE });

		const organization = row(screen.container, 'organization');
		expect(organization.textContent).toContain('Не подтверждено: АО «Компания»');
		expect(organization.textContent).toContain('цитата не найдена в тексте');
		expect(organization.firstElementChild?.classList).toContain('bg-warn-soft');
	});

	it('does not invent values the document has no evidence for', async () => {
		const screen = await render(DocumentCard, { card: CARD, evidence: EVIDENCE });

		expect(row(screen.container, 'approval_number').textContent?.trim()).toBe('нет данных');
	});

	it('lists verified extra attributes', async () => {
		const screen = await render(DocumentCard, { card: CARD, evidence: EVIDENCE });

		await expect.element(screen.getByText('Условие вступления в силу')).toBeVisible();
		await expect.element(screen.getByText('«вступает в силу с даты утверждения»')).toBeVisible();
	});

	it('says so when nothing was extracted', async () => {
		const screen = await render(DocumentCard, { card: EMPTY_CARD, evidence: {} });

		await expect.element(screen.getByText('Реквизиты не извлечены.')).toBeVisible();
		await expect.element(screen.getByText('Название')).not.toBeInTheDocument();
	});
});
