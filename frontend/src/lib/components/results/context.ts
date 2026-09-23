import { createContext } from 'svelte';

import type { ReviewState } from '$lib/result/review.svelte';
import type { JobResult } from '$lib/result/types';

/**
 * The result on screen and the employee's marks on it, shared by every results page, so that a
 * finding confirmed on «Изменения» shows as confirmed on «Анализ» too. Read the fields when they
 * are used: they change when the page moves to another analysis.
 */
export interface ResultsContext {
	readonly result: JobResult;
	readonly review: ReviewState;
}

export const [getResultsContext, setResultsContext] = createContext<ResultsContext>();
