<script lang="ts">
	import '$lib/result/colors.css';
	import { isSourced } from '$lib/result/derive';
	import { CONFIDENCE_LABELS, TYPE_LABELS, VERDICT_LABELS } from '$lib/result/labels';
	import type { ReviewState } from '$lib/result/review.svelte';
	import type { Finding } from '$lib/result/types';

	interface Props {
		/** Findings of the page, in the order the page shows them. */
		findings: Finding[];
		review: ReviewState;
		/** «Открыть» was clicked: show the finding's evidence. */
		onopen: (findingId: string) => void;
	}

	let { findings, review, onopen }: Props = $props();

	/** A finding without a quoted source is not shown here either (I1). */
	const shown = $derived(findings.filter(isSourced));
</script>

<!-- «Показать полную аналитику» under the short conclusion of a page (tz_site.md §6, P1.4). -->
<details class="group">
	<summary class="w-max max-w-full cursor-pointer text-sm font-medium text-accent group-open:mb-2">
		Показать полную аналитику
	</summary>

	{#if shown.length > 0}
		<ul class="grid gap-2" aria-label="Выводы">
			{#each shown as finding (finding.id)}
				{@const verdict = review.verdictOf(finding.id)}
				<li
					class="grid gap-1 rounded-lg border border-l-4 border-line border-l-(--c) bg-surface px-3 py-2.5"
					style:--c={`var(--${finding.type})`}
				>
					<p class="text-[13px] font-semibold text-(--c)">
						{TYPE_LABELS[finding.type]} · {finding.id}
					</p>
					<p class="font-semibold">{finding.title}</p>
					<p class="max-w-[80ch] text-sm">{finding.evidence.conclusion}</p>
					<div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted">
						<span>Уверенность: {CONFIDENCE_LABELS[finding.evidence.confidence]}</span>
						{#if verdict}
							<span
								class={[
									'rounded-full px-2 text-[11px] font-semibold',
									verdict === 'ok' ? 'bg-ok-soft text-ok' : 'bg-bad-soft text-bad'
								]}
							>
								{VERDICT_LABELS[verdict]}
							</span>
						{:else}
							<span>не проверено</span>
						{/if}
						<button
							type="button"
							class="ml-auto rounded-md border border-line bg-page px-2.5 py-1 text-[13px] font-medium text-accent hover:border-accent"
							onclick={() => onopen(finding.id)}
						>
							Открыть<span class="sr-only"> {finding.id}</span>
						</button>
					</div>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="text-sm text-muted">Выводов на этой странице нет.</p>
	{/if}
</details>
