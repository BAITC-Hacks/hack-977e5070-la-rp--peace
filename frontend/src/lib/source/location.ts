import type { SourceLocation } from '$lib/api/sources';

/** A 1-based number as the parser writes pages and spreadsheet rows. */
function isOrdinal(value: unknown): value is number {
	return Number.isInteger(value) && (value as number) >= 1;
}

/** A 0-based index as the DOCX parser writes body items. */
function isIndex(value: unknown): value is number {
	return Number.isInteger(value) && (value as number) >= 0;
}

/**
 * Describes where a source sits in the original file, or returns null when the location is
 * missing or of an unknown shape — an unknown place is left unsaid rather than guessed.
 *
 * DOCX `paragraph` is the backend's 0-based index of body items (paragraphs and tables), so it
 * is shown counted from 1.
 */
export function formatLocation(location: SourceLocation): string | null {
	const { page, paragraph, sheet, row } = location;
	if (isOrdinal(page)) {
		return `стр. ${page}`;
	}
	if (isIndex(paragraph)) {
		return `абзац ${paragraph + 1}`;
	}
	if (typeof sheet === 'string' && sheet.trim() !== '' && isOrdinal(row)) {
		return `лист «${sheet}», строка ${row}`;
	}
	return null;
}
