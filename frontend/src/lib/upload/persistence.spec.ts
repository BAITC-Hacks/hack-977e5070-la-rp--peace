import { describe, expect, it } from 'vitest';

import { readSavedUploads } from './persistence';

const saved = { id: 7, set: 'before', name: 'До.docx', size: 1024 };

describe('readSavedUploads', () => {
	it('keeps document order while removing duplicate ids', () => {
		const after = { ...saved, id: 8, set: 'after' };
		expect(readSavedUploads(JSON.stringify({ version: 1, items: [saved, after, saved] }))).toEqual([
			saved,
			after
		]);
	});

	it.each([
		null,
		'{',
		'null',
		'[]',
		JSON.stringify({ version: 2, items: [saved] }),
		JSON.stringify({ version: 1, items: [{ ...saved, id: -1 }] }),
		JSON.stringify({ version: 1, items: [{ ...saved, set: 'unknown' }] }),
		JSON.stringify({ version: 1, items: [{ ...saved, size: '1024' }] }),
		JSON.stringify({ version: 1, items: [saved, null] })
	])('ignores malformed or unsupported storage: %s', (value) => {
		expect(readSavedUploads(value)).toEqual([]);
	});
});
