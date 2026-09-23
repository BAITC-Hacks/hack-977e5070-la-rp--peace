import { describe, expect, it } from 'vitest';

import { splitContext } from './highlight';

const context = '3.4. Служба проводит аудит системы.';

describe('splitContext', () => {
	it('cuts the quote out of the middle', () => {
		expect(splitContext(context, 12, 26)).toEqual({
			before: '3.4. Служба ',
			quote: 'проводит аудит',
			after: ' системы.'
		});
	});

	it('handles a quote at either edge', () => {
		expect(splitContext(context, 0, 4)).toEqual({
			before: '',
			quote: '3.4.',
			after: ' Служба проводит аудит системы.'
		});
		expect(splitContext(context, 27, context.length)).toEqual({
			before: '3.4. Служба проводит аудит ',
			quote: 'системы.',
			after: ''
		});
	});

	it('marks the whole text when the node is cited as a whole', () => {
		expect(splitContext(context, 0, context.length)).toEqual({
			before: '',
			quote: context,
			after: ''
		});
	});

	it('returns empty parts for an empty context', () => {
		expect(splitContext('', 0, 0)).toEqual({ before: '', quote: '', after: '' });
	});

	it('keeps an empty span empty', () => {
		expect(splitContext(context, 5, 5)).toEqual({
			before: '3.4. ',
			quote: '',
			after: 'Служба проводит аудит системы.'
		});
	});

	it('counts offsets in code points, as the backend does', () => {
		// «𝐀» is one code point but two UTF-16 units.
		const text = '𝐀 проводит аудит';

		expect(splitContext(text, 2, 10)).toEqual({ before: '𝐀 ', quote: 'проводит', after: ' аудит' });
	});

	it('highlights nothing when the offsets do not fit the text', () => {
		const untouched = { before: context, quote: '', after: '' };

		expect(splitContext(context, -1, 4)).toEqual(untouched);
		expect(splitContext(context, 10, 4)).toEqual(untouched);
		expect(splitContext(context, 0, context.length + 1)).toEqual(untouched);
		expect(splitContext(context, 1.5, 4)).toEqual(untouched);
		expect(splitContext(context, Number.NaN, 4)).toEqual(untouched);
	});
});
