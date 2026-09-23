<script lang="ts">
	import type { Snippet } from 'svelte';

	import { visibleFindings } from '$lib/result/derive';
	import { ReviewState } from '$lib/result/review.svelte';
	import type { JobResult } from '$lib/result/types';
	import { localReviewStorage, type ReviewStorage } from '$lib/review/storage';

	import { setResultsContext } from './context';
	import ResultsHeader from './ResultsHeader.svelte';
	import type { ResultsSectionId } from './sections';

	interface Props {
		result: JobResult;
		/** Section on screen, marked in the menu. */
		current: ResultsSectionId | null;
		/** Where the employee's marks are kept between visits; the browser's by default. */
		storage?: ReviewStorage;
		children: Snippet;
	}

	let { result, current, storage = localReviewStorage, children }: Props = $props();

	/** One set of marks for all results pages of the analysis, saved under its job id. */
	const review = $derived(
		new ReviewState(visibleFindings(result), { jobId: result.job_id, storage })
	);

	setResultsContext({
		get result() {
			return result;
		},
		get review() {
			return review;
		}
	});
</script>

<div class="grid gap-5">
	<ResultsHeader id={result.job_id} {current} />
	{@render children()}
</div>
