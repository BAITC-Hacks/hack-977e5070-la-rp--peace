import { error } from '@sveltejs/kit';

import fixture from '$lib/fixtures/result.json';

import type { JobResult } from './types';

/** The only analysis with a result until the backend returns real ones: the demo fixture. */
export const DEMO_ANALYSIS_ID = 'demo';

/**
 * Result of the analysis `id`. For now only `demo` has one, from `lib/fixtures/result.json`; this
 * is the one place to switch to `GET /api/analyses/{id}` once the backend returns results.
 */
export function loadResult(id: string): JobResult {
	if (id !== DEMO_ANALYSIS_ID) {
		error(404, 'Результат не найден');
	}
	// JSON imports type enum values as plain strings; src/lib/fixtures/result.spec.ts checks them.
	return fixture as JobResult;
}
