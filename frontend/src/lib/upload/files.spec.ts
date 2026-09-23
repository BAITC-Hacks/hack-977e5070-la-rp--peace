import { describe, expect, it } from 'vitest';

import { extensionOf, formatSize, isAccepted } from './files';

describe('extensionOf', () => {
	it('returns the lower-cased last extension', () => {
		expect(extensionOf('Положение.v9.DOCX')).toBe('.docx');
	});

	it('returns an empty string for names without an extension', () => {
		expect(extensionOf('README')).toBe('');
		expect(extensionOf('.hidden')).toBe('');
	});
});

describe('isAccepted', () => {
	it.each(['a.docx', 'a.doc', 'a.pdf', 'a.xlsx', 'a.xls', 'A.PDF'])('accepts %s', (name) => {
		expect(isAccepted(name)).toBe(true);
	});

	it.each(['a.txt', 'a.docx.zip', 'docx', 'a.'])('rejects %s', (name) => {
		expect(isAccepted(name)).toBe(false);
	});
});

describe('formatSize', () => {
	it('shows bytes below one kilobyte', () => {
		expect(formatSize(512)).toBe('512 Б');
	});

	it('keeps one decimal below ten units', () => {
		expect(formatSize(1536)).toBe('1,5 КБ');
		expect(formatSize(1.5 * 1024 * 1024)).toBe('1,5 МБ');
	});

	it('rounds to whole units from ten upwards', () => {
		expect(formatSize(68_185)).toBe('67 КБ');
	});
});
