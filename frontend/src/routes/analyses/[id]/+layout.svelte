<script lang="ts">
	import { page } from '$app/state';
	import ResultsShell from '$lib/components/results/ResultsShell.svelte';
	import { sectionOfRoute } from '$lib/components/results/sections';

	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();
</script>

<ResultsShell result={data.result} current={sectionOfRoute(page.route.id)}>
	{@render children()}
</ResultsShell>
