<script lang="ts">
	import '$lib/result/colors.css';
	import { countByType, splitConclusion, visibleFindings } from '$lib/result/derive';
	import { TYPE_LABELS } from '$lib/result/labels';
	import type { ReviewState } from '$lib/result/review.svelte';
	import type { JobResult } from '$lib/result/types';

	interface Props {
		result: JobResult;
		review: ReviewState;
		/** A finding mentioned in the conclusion was clicked. */
		onopen: (findingId: string) => void;
	}

	let { result, review, onopen }: Props = $props();

	const headingId = $props.id();
	const shown = $derived(visibleFindings(result));
	/** Only findings that are shown become links (I1). */
	const parts = $derived(
		splitConclusion(result.conclusion, new Set(shown.map((finding) => finding.id)))
	);
	const counts = $derived(countByType(shown));
</script>

<section
	class="grid gap-2.5 rounded-lg border border-line bg-surface px-4 py-3.5"
	aria-labelledby={headingId}
>
	<div class="flex flex-wrap items-center gap-x-4 gap-y-2">
		<h2 id={headingId} class="font-semibold">Сводка изменений</h2>
		<button
			type="button"
			data-print="hide"
			class="ml-auto rounded-md border border-line bg-page px-2.5 py-1 text-[13px] font-medium text-accent hover:border-accent"
			onclick={() => window.print()}
		>
			Скачать PDF
		</button>
	</div>

	{#if parts.length > 0}
		<p class="max-w-[80ch]">
			{#each parts as part, index (index)}
				{#if part.kind === 'finding'}
					<button
						type="button"
						class="rounded font-mono text-[0.9em] text-accent underline underline-offset-2"
						onclick={() => onopen(part.id)}
					>
						{part.id}
					</button>
				{:else}
					{part.text}
				{/if}
			{/each}
		</p>
	{/if}

	{#if result.summary.changed_blocks.length > 0}
		<p class="text-sm">
			<span class="text-muted">Изменённые блоки:</span>
			{result.summary.changed_blocks.join(' · ')}
		</p>
	{/if}

	{#if counts.length > 0}
		<ul class="flex flex-wrap gap-2" aria-label="Находки по типам">
			{#each counts as { type, count } (type)}
				<li
					class="inline-flex items-center gap-1.5 rounded-full bg-neutral-soft px-2.5 py-0.5 text-[13px]"
				>
					<span class="size-2 rounded-full bg-(--c)" style:--c={`var(--${type})`}></span>
					{TYPE_LABELS[type]}: {count}
				</li>
			{/each}
		</ul>
	{/if}

	<p class="text-sm text-muted">Проверено сотрудником: {review.reviewed} из {review.total}</p>
</section>
