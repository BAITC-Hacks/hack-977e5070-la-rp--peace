import { describe, expect, it } from 'vitest';

import type { Confidence, Finding, FindingType } from '$lib/result/types';

import { CAPPED_NOTE, shownConfidence, withShownConfidence } from './confidence';

function finding(type: FindingType, confidence: Confidence, note: string | null = null): Finding {
	return {
		id: 'C-020',
		type,
		block: 'IT и цифровизация',
		title: 'Находка',
		from: [],
		to: [],
		evidence: {
			conclusion: 'Вывод',
			method: 'Метод',
			steps: [],
			confidence,
			confidence_note: note
		},
		review: null
	};
}

describe('shownConfidence', () => {
	it('lowers a high confidence of overlaps and contradictions to medium (P1.5)', () => {
		expect(shownConfidence(finding('overlap', 'high'))).toBe('medium');
		expect(shownConfidence(finding('contradiction', 'high'))).toBe('medium');
	});

	it('keeps medium and low confidence of overlaps and contradictions', () => {
		expect(shownConfidence(finding('overlap', 'medium'))).toBe('medium');
		expect(shownConfidence(finding('contradiction', 'low'))).toBe('low');
	});

	it('leaves the other types as they are', () => {
		expect(shownConfidence(finding('conflict', 'high'))).toBe('high');
		expect(shownConfidence(finding('loss', 'high'))).toBe('high');
		expect(shownConfidence(finding('duplication', 'low'))).toBe('low');
	});
});

describe('withShownConfidence', () => {
	it('returns the same finding when nothing is lowered', () => {
		const conflict = finding('conflict', 'high', 'Основание');
		const overlap = finding('overlap', 'medium', 'Основание');

		expect(withShownConfidence(conflict)).toBe(conflict);
		expect(withShownConfidence(overlap)).toBe(overlap);
	});

	it('copies a lowered finding and explains the cap after the basis', () => {
		const contradiction = finding('contradiction', 'high', 'Факты подтверждены цитатами.');

		const shown = withShownConfidence(contradiction);

		expect(shown).not.toBe(contradiction);
		expect(shown.evidence.confidence).toBe('medium');
		expect(shown.evidence.confidence_note).toBe(`Факты подтверждены цитатами. ${CAPPED_NOTE}`);
		expect(contradiction.evidence.confidence).toBe('high');
	});

	it('uses the cap explanation alone when there is no basis', () => {
		const shown = withShownConfidence(finding('overlap', 'high'));

		expect(shown.evidence.confidence_note).toBe(CAPPED_NOTE);
	});
});
