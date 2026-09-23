import type { JobResult } from '$lib/result/types';

import { request } from './client';

/** Where a before → after comparison stands; `result` is filled once it is done. */
export type ComparisonStatus = 'pending' | 'running' | 'done' | 'needs_review' | 'failed';

export interface ComparisonOut {
	id: number;
	before_ids: number[];
	after_ids: number[];
	status: ComparisonStatus;
	error: string | null;
	created_at: string;
	result: JobResult | null;
}

/** Statuses after which the comparison no longer changes. */
export const FINISHED: readonly ComparisonStatus[] = ['done', 'needs_review', 'failed'];

/** `POST /api/comparisons`: starts the analysis; it waits for both sides' stages by itself. */
export async function startComparison(
	beforeIds: number[],
	afterIds: number[]
): Promise<ComparisonOut> {
	const response = await request('/api/comparisons', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ before_ids: beforeIds, after_ids: afterIds })
	});
	return (await response.json()) as ComparisonOut;
}

/** `GET /api/comparisons/{id}`. */
export async function getComparison(id: number | string): Promise<ComparisonOut> {
	const response = await request(`/api/comparisons/${id}`);
	return (await response.json()) as ComparisonOut;
}
