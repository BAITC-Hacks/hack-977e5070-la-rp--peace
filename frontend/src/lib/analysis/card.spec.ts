import { describe, expect, it } from 'vitest';

import type { Finding } from '$lib/result/types';

import { cardTitle } from './card';

function finding(type: Finding['type'], title: string): Finding {
	return {
		id: 'C-011',
		type,
		block: 'ИБ и режим',
		title,
		from: [],
		to: [],
		evidence: { conclusion: 'Вывод', method: 'Метод', steps: [], confidence: 'high' },
		review: null
	};
}

describe('cardTitle', () => {
	it('keeps a title that says more than the type', () => {
		expect(cardTitle(finding('loss', ' Мобилизационная подготовка '))).toBe(
			'Мобилизационная подготовка'
		);
	});

	it('drops a title that only repeats the type label, whatever the case', () => {
		expect(cardTitle(finding('loss', 'Потеря функции'))).toBeNull();
		expect(cardTitle(finding('contradiction', 'противоречие функций'))).toBeNull();
	});

	it('drops an empty title', () => {
		expect(cardTitle(finding('overlap', '  '))).toBeNull();
	});
});
