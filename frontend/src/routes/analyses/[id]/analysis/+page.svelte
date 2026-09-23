<script lang="ts">
	import { tick } from 'svelte';

	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import type { AnalysisTabId } from '$lib/analysis/tabs';
	import AnalysisView from '$lib/components/analysis/AnalysisView.svelte';
	import { tabFromQuery, tabQuery } from '$lib/components/analysis/query';
	import { getResultsContext } from '$lib/components/results/context';
	import type { Source } from '$lib/result/types';
	import { flashItem } from '$lib/visual/flash';

	const results = getResultsContext();

	/** The open sub-page lives in `?tab=`, so a link opens the same one. */
	const tab = $derived(tabFromQuery(page.url.searchParams));

	function selectTab(next: AnalysisTabId) {
		const query = tabQuery(page.url.searchParams, next);
		goto(resolve(`/analyses/[id]/analysis${query}`, { id: results.result.job_id }), {
			replaceState: true,
			keepFocus: true,
			noScroll: true
		});
	}

	/** A quote in the evidence: show the item it is about on «Изменения». */
	async function showQuote(source: Source) {
		await goto(resolve('/analyses/[id]/changes', { id: results.result.job_id }));
		if (source.item !== null) {
			await tick();
			flashItem(source.item);
		}
	}
</script>

<svelte:head>
	<title>Анализ — Анализ реорганизации</title>
</svelte:head>

<AnalysisView
	result={results.result}
	review={results.review}
	onquote={showQuote}
	bind:tab={() => tab, selectTab}
/>
