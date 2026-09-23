<script lang="ts">
	import { blockFindings } from '$lib/result/derive';
	import { DOC_LABELS } from '$lib/result/labels';
	import type { ReviewState } from '$lib/result/review.svelte';
	import type { JobResult } from '$lib/result/types';

	import BlockRow from './BlockRow.svelte';

	interface Props {
		result: JobResult;
		review: ReviewState;
		/** A card was clicked: open the evidence of this finding. */
		onopen: (findingId: string) => void;
	}

	let { result, review, onopen }: Props = $props();

	/** Findings without a source are left out (I1); their column items stay. */
	const rows = $derived(
		result.blocks.map((block) => ({ block, findings: blockFindings(block, result.findings) }))
	);
</script>

<!-- «Изменения → Визуал», after docs/spec/visual_compare.html; laid out for 1024 px and wider. -->
<div class="grid">
	<div
		class="grid grid-cols-[1fr_minmax(240px,300px)_1fr] gap-x-12 text-xs font-semibold tracking-[0.08em] text-muted uppercase"
		aria-hidden="true"
	>
		<div>{DOC_LABELS.before}</div>
		<div>Изменения</div>
		<div>{DOC_LABELS.after}</div>
	</div>
	{#each rows as row (row.block.title)}
		<BlockRow block={row.block} findings={row.findings} {review} {onopen} />
	{/each}
</div>
