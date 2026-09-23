import { analysisRunApi } from '$lib/api/analyses';

import { AnalysisRun } from './analysis-run.svelte';

/**
 * The analysis run of the status screen. One for the whole app, like the upload session it
 * follows, so that coming back to the screen shows the same run instead of starting another.
 */
export const analysisRun = new AnalysisRun(analysisRunApi);
