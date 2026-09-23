import type { DocumentCardValues } from '$lib/api/document';

export type CardFieldName = keyof DocumentCardValues;

/** Card rows in display order (backend `CARD_FIELDS`, ingestion/metadata.py). */
export const CARD_FIELDS: readonly { name: CardFieldName; label: string; isDate: boolean }[] = [
	{ name: 'title', label: 'Название', isDate: false },
	{ name: 'document_type', label: 'Тип документа', isDate: false },
	{ name: 'organization', label: 'Организация', isDate: false },
	{ name: 'revision', label: 'Редакция', isDate: false },
	{ name: 'approved_by', label: 'Кем утверждён', isDate: false },
	{ name: 'approval_document_type', label: 'Вид документа об утверждении', isDate: false },
	{ name: 'approval_number', label: 'Номер документа об утверждении', isDate: false },
	{ name: 'document_created_on', label: 'Дата составления', isDate: true },
	{ name: 'approved_on', label: 'Дата утверждения', isDate: true },
	{ name: 'effective_from', label: 'Вступает в силу', isDate: true }
];

/**
 * - `confirmed`: the backend found every quote in the text and accepted the value;
 * - `manual`: the value was set by a person, so the model's quotes do not back it;
 * - `not_found`: the model reports the document does not state it;
 * - `ambiguous`: the model's value was not accepted, `reason` says why;
 * - `unknown`: there is no evidence for the field at all (e.g. parsing failed).
 */
export type FieldState = 'confirmed' | 'manual' | 'not_found' | 'ambiguous' | 'unknown';

export interface CardField {
	name: CardFieldName;
	label: string;
	state: FieldState;
	/** The accepted value, or for `ambiguous` the model's unconfirmed candidate, if any. */
	value: string | null;
	/** Verbatim fragments of the document that support the value. */
	quotes: string[];
	reason: string | null;
}

/** A document attribute outside the card, e.g. the condition for entering into force. */
export interface ExtraField {
	name: string;
	value: string;
	quotes: string[];
}

function asRecord(value: unknown): Record<string, unknown> | null {
	return typeof value === 'object' && value !== null && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: null;
}

function asText(value: unknown): string | null {
	return typeof value === 'string' && value.trim() !== '' ? value : null;
}

/** Distinct quote texts of an evidence entry: `[{text, start, end}]` as stored by the backend. */
function quoteTexts(value: unknown): string[] {
	if (!Array.isArray(value)) {
		return [];
	}
	const texts = value
		.map((quote: unknown) => asText(asRecord(quote)?.text ?? quote))
		.filter((text): text is string => text !== null);
	return [...new Set(texts)];
}

/** «23.12.2022» for an ISO date; anything else is returned unchanged. */
export function formatDate(value: string): string {
	const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
	return match ? `${match[3]}.${match[2]}.${match[1]}` : value;
}

/**
 * Card rows with their evidence (`GET /profile` → `metadata_evidence`). A value is shown only
 * when the backend accepted it; for the rest the model's status and reason are shown instead.
 */
export function cardFields(
	document: DocumentCardValues,
	evidence: Record<string, unknown>
): CardField[] {
	return CARD_FIELDS.map(({ name, label, isDate }) => {
		const entry = asRecord(evidence[name]);
		const status = entry?.status;
		const reported = asText(entry?.value);
		const accepted = document[name];
		const field: CardField = {
			name,
			label,
			state: 'unknown',
			value: null,
			quotes: [],
			reason: asText(entry?.reason)
		};
		if (accepted !== null) {
			const backed = status === 'extracted' && reported === accepted;
			field.state = backed ? 'confirmed' : 'manual';
			field.value = accepted;
			field.quotes = backed ? quoteTexts(entry?.quotes) : [];
		} else if (status === 'not_found') {
			field.state = 'not_found';
		} else if (status === 'ambiguous') {
			field.state = 'ambiguous';
			field.value = reported;
			field.quotes = quoteTexts(entry?.quotes);
		}
		if (isDate && field.value !== null) {
			field.value = formatDate(field.value);
		}
		return field;
	});
}

/** Whether the card has nothing to show: no values and no evidence for any field. */
export function isCardEmpty(fields: readonly CardField[]): boolean {
	return fields.every((field) => field.state === 'unknown');
}

/** Key of an extra attribute; `extraFields` never returns two with the same key. */
export function extraKey(field: ExtraField): string {
	return `${field.name}\n${field.value}`;
}

/** Attributes outside the card that the backend verified against the text. */
export function extraFields(evidence: Record<string, unknown>): ExtraField[] {
	const extra = evidence.extra;
	if (!Array.isArray(extra)) {
		return [];
	}
	const fields = new Map<string, ExtraField>();
	for (const item of extra) {
		const entry = asRecord(item);
		const name = asText(entry?.name);
		const value = asText(entry?.value);
		const quotes = quoteTexts(entry?.quotes);
		if (name !== null && value !== null && quotes.length > 0) {
			const field = { name, value, quotes };
			const key = extraKey(field);
			if (!fields.has(key)) {
				fields.set(key, field);
			}
		}
	}
	return [...fields.values()];
}
