import { describe, expect, it } from 'vitest';

import type { DocumentCardValues } from '$lib/api/document';

import { cardFields, extraFields, formatDate, isCardEmpty, type CardField } from './card';

const quote = (text: string, start = 0) => ({ text, start, end: start + text.length });

// Evidence as the backend stores it for ed. 9 (tests/fixtures/profiles/metadata_ed9.json on main,
// after verification), with one value rejected by the quote check.
const EVIDENCE: Record<string, unknown> = {
	title: {
		status: 'extracted',
		value: 'Положение о внутреннем аудите АО «Компания»',
		quotes: [quote('ПОЛОЖЕНИЕ О ВНУТРЕННЕМ АУДИТЕ АО «Компания»', 40)]
	},
	document_type: { status: 'extracted', value: 'положение', quotes: [quote('ПОЛОЖЕНИЕ', 40)] },
	organization: {
		status: 'ambiguous',
		value: 'АО «Компания»',
		quotes: [],
		reason: 'цитата не найдена в тексте: «АО Компания»',
		rejected_quotes: ['АО Компания']
	},
	revision: { status: 'extracted', value: '9', quotes: [quote('(редакция No9)', 90)] },
	approved_by: { status: 'not_found', value: null, quotes: [] },
	approved_on: {
		status: 'extracted',
		value: '2022-12-23',
		quotes: [quote('от «23» декабря 2022 года', 10)]
	},
	effective_from: {
		status: 'not_found',
		value: null,
		quotes: [],
		reason: 'п. 13.2 связывает вступление в силу с утверждением, календарная дата не указана'
	},
	extra: [
		{
			name: 'Условие вступления в силу',
			value: 'с даты утверждения',
			quotes: [quote('вступает в силу с даты утверждения', 500)]
		}
	]
};

const CARD: DocumentCardValues = {
	title: 'Положение о внутреннем аудите АО «Компания»',
	document_type: 'положение',
	organization: null,
	revision: '9',
	approved_by: null,
	approval_document_type: null,
	approval_number: null,
	document_created_on: null,
	approved_on: '2022-12-23',
	effective_from: null
};

function field(fields: CardField[], name: CardField['name']): CardField {
	const found = fields.find((item) => item.name === name);
	if (found === undefined) {
		throw new Error(`no field ${name}`);
	}
	return found;
}

describe('cardFields', () => {
	it('lists every card field in order', () => {
		expect(cardFields(CARD, EVIDENCE).map((item) => item.label)).toEqual([
			'Название',
			'Тип документа',
			'Организация',
			'Редакция',
			'Кем утверждён',
			'Вид документа об утверждении',
			'Номер документа об утверждении',
			'Дата составления',
			'Дата утверждения',
			'Вступает в силу'
		]);
	});

	it('shows an accepted value with its quotes', () => {
		expect(field(cardFields(CARD, EVIDENCE), 'revision')).toEqual({
			name: 'revision',
			label: 'Редакция',
			state: 'confirmed',
			value: '9',
			quotes: ['(редакция No9)'],
			reason: null
		});
	});

	it('formats accepted dates', () => {
		const approved = field(cardFields(CARD, EVIDENCE), 'approved_on');

		expect(approved.value).toBe('23.12.2022');
		expect(approved.quotes).toEqual(['от «23» декабря 2022 года']);
	});

	it('marks a missing value as not found, with the reason when given', () => {
		const fields = cardFields(CARD, EVIDENCE);

		expect(field(fields, 'approved_by')).toMatchObject({ state: 'not_found', reason: null });
		expect(field(fields, 'effective_from')).toMatchObject({
			state: 'not_found',
			value: null,
			reason: 'п. 13.2 связывает вступление в силу с утверждением, календарная дата не указана'
		});
	});

	it('keeps a rejected value as an unconfirmed candidate with the reason', () => {
		expect(field(cardFields(CARD, EVIDENCE), 'organization')).toEqual({
			name: 'organization',
			label: 'Организация',
			state: 'ambiguous',
			value: 'АО «Компания»',
			quotes: [],
			reason: 'цитата не найдена в тексте: «АО Компания»'
		});
	});

	it('does not invent anything for a field without evidence', () => {
		expect(field(cardFields(CARD, EVIDENCE), 'approval_number')).toEqual({
			name: 'approval_number',
			label: 'Номер документа об утверждении',
			state: 'unknown',
			value: null,
			quotes: [],
			reason: null
		});
	});

	it('drops the model quotes when a person changed the value', () => {
		const corrected = { ...CARD, document_type: 'Положение о подразделении' };

		expect(field(cardFields(corrected, EVIDENCE), 'document_type')).toMatchObject({
			state: 'manual',
			value: 'Положение о подразделении',
			quotes: []
		});
	});

	it('lists a quote cited twice once', () => {
		const fields = cardFields(CARD, {
			revision: { status: 'extracted', value: '9', quotes: [quote('No9'), quote('No9', 400)] }
		});

		expect(field(fields, 'revision').quotes).toEqual(['No9']);
	});

	it('ignores malformed evidence', () => {
		const fields = cardFields(CARD, {
			title: 'не объект',
			revision: { status: 'extracted', value: '9', quotes: [{ start: 1 }, 42, quote('  ')] }
		});

		expect(field(fields, 'title')).toMatchObject({ state: 'manual', quotes: [] });
		expect(field(fields, 'revision')).toMatchObject({ state: 'confirmed', quotes: [] });
	});
});

describe('isCardEmpty', () => {
	it('is true only when no field has a value or evidence', () => {
		const empty: DocumentCardValues = { ...CARD, title: null, document_type: null };
		const bare = { ...empty, revision: null, approved_on: null };

		expect(isCardEmpty(cardFields(bare, {}))).toBe(true);
		expect(isCardEmpty(cardFields(bare, EVIDENCE))).toBe(false);
		expect(isCardEmpty(cardFields(CARD, {}))).toBe(false);
	});
});

describe('extraFields', () => {
	it('returns verified extra attributes', () => {
		expect(extraFields(EVIDENCE)).toEqual([
			{
				name: 'Условие вступления в силу',
				value: 'с даты утверждения',
				quotes: ['вступает в силу с даты утверждения']
			}
		]);
	});

	it('keeps the first of repeated attributes', () => {
		const repeated = { name: 'Срок', value: 'год', quotes: [quote('сроком на год')] };

		expect(
			extraFields({ extra: [repeated, { ...repeated, quotes: [quote('на один год')] }] })
		).toEqual([{ name: 'Срок', value: 'год', quotes: ['сроком на год'] }]);
	});

	it('skips entries without a name, value or quote', () => {
		expect(
			extraFields({
				extra: [
					{ name: 'Срок', value: '', quotes: [quote('год')] },
					{ name: 'Срок', value: 'год' }
				]
			})
		).toEqual([]);
		expect(extraFields({})).toEqual([]);
	});
});

describe('formatDate', () => {
	it('turns an ISO date into the Russian form and leaves other text alone', () => {
		expect(formatDate('2022-12-23')).toBe('23.12.2022');
		expect(formatDate('23 декабря 2022')).toBe('23 декабря 2022');
	});
});
