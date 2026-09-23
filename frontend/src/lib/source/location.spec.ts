import { describe, expect, it } from 'vitest';

import { formatLocation } from './location';

describe('formatLocation', () => {
	it('names the page of a PDF', () => {
		expect(formatLocation({ page: 6 })).toBe('стр. 6');
	});

	it('counts DOCX paragraphs from 1', () => {
		expect(formatLocation({ paragraph: 102 })).toBe('абзац 103');
		expect(formatLocation({ paragraph: 0 })).toBe('абзац 1');
	});

	it('names the sheet and row of a spreadsheet', () => {
		expect(formatLocation({ sheet: 'Штатное расписание', row: 12 })).toBe(
			'лист «Штатное расписание», строка 12'
		);
	});

	it('ignores extra keys next to a known place', () => {
		expect(formatLocation({ paragraph: 40, table_row: 3, column: 2 })).toBe('абзац 41');
		expect(formatLocation({ sheet: 'Штат', row: 5, column: 'C' })).toBe('лист «Штат», строка 5');
	});

	it('says nothing about an unknown or incomplete place', () => {
		expect(formatLocation({})).toBeNull();
		expect(formatLocation({ slide: 3 })).toBeNull();
		expect(formatLocation({ sheet: 'Штат' })).toBeNull();
		expect(formatLocation({ sheet: '  ', row: 5 })).toBeNull();
		expect(formatLocation({ row: 5 })).toBeNull();
	});

	it('says nothing about malformed numbers', () => {
		expect(formatLocation({ page: 0 })).toBeNull();
		expect(formatLocation({ page: '6' })).toBeNull();
		expect(formatLocation({ page: 2.5 })).toBeNull();
		expect(formatLocation({ paragraph: -1 })).toBeNull();
		expect(formatLocation({ paragraph: null })).toBeNull();
		expect(formatLocation({ sheet: 'Штат', row: 0 })).toBeNull();
	});
});
