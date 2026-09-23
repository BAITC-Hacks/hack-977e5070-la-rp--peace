<script lang="ts">
	import type { JobResult } from '$lib/result/types';
	import type { ReviewStorage } from '$lib/review/storage';

	import AnalysisPage from '../../../routes/analyses/[id]/analysis/+page.svelte';
	import ChangesPage from '../../../routes/analyses/[id]/changes/+page.svelte';

	import ResultsShell from './ResultsShell.svelte';
	import type { ResultsSectionId } from './sections';

	interface Props {
		result: JobResult;
		storage: ReviewStorage;
		/** Results pages to render in the shell, in this order. */
		pages: readonly ResultsSectionId[];
	}

	let { result, storage, pages }: Props = $props();
</script>

<!-- Test harness for ResultsShell.svelte.spec.ts: the real results pages inside one shell. -->
<ResultsShell {result} {storage} current={pages[0] ?? null}>
	{#each pages as section (section)}
		<section data-page={section}>
			{#if section === 'changes'}
				<ChangesPage />
			{:else if section === 'analysis'}
				<AnalysisPage />
			{/if}
		</section>
	{/each}
</ResultsShell>
