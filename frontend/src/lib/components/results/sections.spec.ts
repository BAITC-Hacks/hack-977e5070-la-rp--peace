import { describe, expect, it } from 'vitest';

import { RESULTS_SECTIONS, sectionOfRoute } from './sections';

describe('results sections', () => {
	it('are «Изменения · Анализ · Чат», with the chat not built yet', () => {
		expect(RESULTS_SECTIONS.map((section) => [section.label, section.enabled])).toEqual([
			['Изменения', true],
			['Анализ', true],
			['Чат', false]
		]);
	});

	it('are found by route', () => {
		expect(sectionOfRoute('/analyses/[id]/changes')).toBe('changes');
		expect(sectionOfRoute('/analyses/[id]/analysis')).toBe('analysis');
		expect(sectionOfRoute('/analyses/[id]')).toBeNull();
		expect(sectionOfRoute('/status')).toBeNull();
		expect(sectionOfRoute(null)).toBeNull();
	});
});
