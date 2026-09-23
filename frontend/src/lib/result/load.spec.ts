import { isHttpError } from '@sveltejs/kit';
import { describe, expect, it } from 'vitest';

import fixture from '$lib/fixtures/result.json';

import { DEMO_ANALYSIS_ID, loadResult } from './load';

function failureOf(id: string): unknown {
	try {
		loadResult(id);
	} catch (caught) {
		return caught;
	}
	return null;
}

describe('loadResult', () => {
	it('gives the demo fixture for the demo analysis', () => {
		const result = loadResult(DEMO_ANALYSIS_ID);

		expect(result).toBe(fixture);
		expect(result.job_id).toBe(DEMO_ANALYSIS_ID);
	});

	it.each(['42', 'Demo', ''])('answers 404 «Результат не найден» for «%s»', (id) => {
		const failure = failureOf(id);

		expect(isHttpError(failure, 404)).toBe(true);
		expect(isHttpError(failure) && failure.body.message).toBe('Результат не найден');
	});
});
