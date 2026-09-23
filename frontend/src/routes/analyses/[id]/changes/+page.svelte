<script lang="ts">
	import ChangesView from '$lib/components/changes/ChangesView.svelte';
	import { getResultsContext } from '$lib/components/results/context';

	const results = getResultsContext();
</script>

<svelte:head>
	<title>Изменения — Анализ реорганизации</title>
</svelte:head>

<ChangesView result={results.result} review={results.review} />
