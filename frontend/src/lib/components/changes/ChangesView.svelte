<script lang="ts">
	import EvidenceDrawer from '$lib/components/evidence/EvidenceDrawer.svelte';
	import FullAnalytics from '$lib/components/full/FullAnalytics.svelte';
	import SummaryPanel from '$lib/components/summary/SummaryPanel.svelte';
	import VisualCompare from '$lib/components/visual/VisualCompare.svelte';
	import { visibleFindings } from '$lib/result/derive';
	import { ReviewState } from '$lib/result/review.svelte';
	import type { JobResult, Source } from '$lib/result/types';
	import { localReviewStorage, type ReviewStorage } from '$lib/review/storage';
	import { flashItem } from '$lib/visual/flash';

	interface Props {
		result: JobResult;
		/** Where the employee's marks are kept between visits; the browser's by default. */
		storage?: ReviewStorage;
	}

	let { result, storage = localReviewStorage }: Props = $props();

	const findings = $derived(visibleFindings(result));
	const review = $derived(new ReviewState(findings, { jobId: result.job_id, storage }));
	let openId = $state<string | null>(null);
	const finding = $derived(openId === null ? null : (result.findings[openId] ?? null));

	function open(findingId: string) {
		openId = findingId;
	}

	/** A quote in the evidence panel: close the panel and show the item the quote is about. */
	function showQuote(source: Source) {
		openId = null;
		if (source.item !== null) {
			flashItem(source.item);
		}
	}
</script>

<!--
	«Изменения → Визуал» (tz_site.md §6.3): summary, «Показать полную аналитику», the three-column
	comparison and the evidence panel. Not routed yet: /analyses/[id] gets it once the backend
	returns real results.
-->
<div class="grid gap-5">
	<SummaryPanel {result} {review} onopen={open} />
	<FullAnalytics {findings} {review} onopen={open} />
	<VisualCompare {result} {review} onopen={open} />
</div>

<EvidenceDrawer {finding} {review} onclose={() => (openId = null)} onquote={showQuote} />
