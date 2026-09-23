import { describe, expect, it } from 'vitest';

import { MAX_LCS_CELLS, diffWords, tokenize, type WordPart } from './words';

function side(parts: readonly WordPart[], skip: WordPart['op']): string {
	return parts
		.filter((part) => part.op !== skip)
		.map((part) => part.text)
		.join('');
}

describe('tokenize', () => {
	it('keeps every character: words, spaces and punctuation', () => {
		expect(tokenize('Отдел кадров, п. 3.4')).toEqual([
			'Отдел',
			' ',
			'кадров',
			',',
			' ',
			'п',
			'.',
			' ',
			'3',
			'.',
			'4'
		]);
	});
});

describe('diffWords', () => {
	it('returns one kept part for equal texts and nothing for two empty ones', () => {
		expect(diffWords('Управление IT', 'Управление IT')).toEqual([
			{ op: 'equal', text: 'Управление IT' }
		]);
		expect(diffWords('', '')).toEqual([]);
	});

	it('marks an inserted phrase inside the text', () => {
		expect(
			diffWords(
				'Департамент информационной безопасности подчиняется заместителю.',
				'Департамент информационной безопасности и режима подчиняется заместителю.'
			)
		).toEqual([
			{ op: 'equal', text: 'Департамент информационной безопасности ' },
			{ op: 'insert', text: 'и режима ' },
			{ op: 'equal', text: 'подчиняется заместителю.' }
		]);
	});

	it('marks a deleted word', () => {
		expect(diffWords('Отдел режима, Управление закупок', 'Управление закупок')).toEqual([
			{ op: 'delete', text: 'Отдел режима, ' },
			{ op: 'equal', text: 'Управление закупок' }
		]);
	});

	it('shows a replaced phrase as one deletion followed by one insertion', () => {
		expect(
			diffWords(
				'Отдел кадров организует обучение работников.',
				'Департамент персонала организует обучение работников.'
			)
		).toEqual([
			{ op: 'delete', text: 'Отдел кадров' },
			{ op: 'insert', text: 'Департамент персонала' },
			{ op: 'equal', text: ' организует обучение работников.' }
		]);
	});

	it('keeps changed numbers as whole tokens', () => {
		expect(diffWords('Общая численность: 214 ед.', 'Общая численность: 198 ед.')).toEqual([
			{ op: 'equal', text: 'Общая численность: ' },
			{ op: 'delete', text: '214' },
			{ op: 'insert', text: '198' },
			{ op: 'equal', text: ' ед.' }
		]);
	});

	it('always rebuilds both texts from its parts', () => {
		const pairs = [
			['а) проводит аудит; б) ведёт учёт', 'а) ведёт учёт; б) проводит аудит системы'],
			['', 'Новый пункт.'],
			['Удалённый пункт.', ''],
			['Текст  с   пробелами', 'Текст с пробелами и словом']
		];
		for (const [before, after] of pairs) {
			const parts = diffWords(before, after);
			expect(side(parts, 'insert')).toBe(before);
			expect(side(parts, 'delete')).toBe(after);
		}
	});

	it('shows the differing middle of very long texts replaced as a whole', () => {
		const words = Math.ceil(Math.sqrt(MAX_LCS_CELLS));
		const before = Array.from({ length: words }, (_, i) => `старое${i}`).join(' ');
		const after = Array.from({ length: words }, (_, i) => `новое${i}`).join(' ');

		expect(diffWords(before, after)).toEqual([
			{ op: 'delete', text: before },
			{ op: 'insert', text: after }
		]);
		expect(diffWords(`Начало. ${before}`, `Начало. ${after}`)).toEqual([
			{ op: 'equal', text: 'Начало. ' },
			{ op: 'delete', text: before },
			{ op: 'insert', text: after }
		]);
	});
});
