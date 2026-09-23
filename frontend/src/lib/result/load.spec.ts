import { isHttpError } from '@sveltejs/kit';
import { describe, expect, it } from 'vitest';

import fixture from '$lib/fixtures/result.json';

import { DEMO_ANALYSIS_ID, loadResult } from './load';

async function failureOf(id: string): Promise<unknown> {
	try {
		await loadResult(id);
	} catch (caught) {
		return caught;
	}
	return null;
}

describe('loadResult', () => {
	it('gives the demo fixture for the demo analysis', async () => {
		const result = await loadResult(DEMO_ANALYSIS_ID);

		expect(result).toBe(fixture);
		expect(result.job_id).toBe(DEMO_ANALYSIS_ID);
	});

	// Numeric ids are backend comparisons; anything else is not an analysis at all.
	it.each(['Demo', ''])('answers 404 «Результат не найден» for «%s»', async (id) => {
		const failure = await failureOf(id);

		expect(isHttpError(failure, 404)).toBe(true);
		expect(isHttpError(failure) && failure.body.message).toBe('Результат не найден');
	});
});
