import { error } from '@sveltejs/kit';

import { ApiError } from '$lib/api/errors';
import { getComparison } from '$lib/api/comparisons';
import fixture from '$lib/fixtures/result.json';

import type { JobResult } from './types';

/** The demo analysis, served from `lib/fixtures/result.json`. */
export const DEMO_ANALYSIS_ID = 'demo';

/** Result of the analysis `id`: the demo fixture, or the backend comparison with that id. */
export async function loadResult(id: string): Promise<JobResult> {
	if (id === DEMO_ANALYSIS_ID) {
		// JSON imports type enum values as plain strings; src/lib/fixtures/result.spec.ts checks them.
		return fixture as JobResult;
	}
	if (!/^\d+$/.test(id)) {
		error(404, 'Результат не найден');
	}
	try {
		const comparison = await getComparison(id);
		if (comparison.result === null) {
			error(404, comparison.error ?? 'Анализ ещё не завершён');
		}
		return comparison.result;
	} catch (cause) {
		if (cause instanceof ApiError) {
			error(cause.status === 404 ? 404 : 502, cause.message);
		}
		throw cause;
	}
}
