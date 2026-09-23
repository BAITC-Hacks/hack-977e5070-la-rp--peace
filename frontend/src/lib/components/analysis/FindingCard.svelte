<script lang="ts">
	import '$lib/result/colors.css';
	import { cardTitle } from '$lib/analysis/card';
	import { CONFIDENCE_LABELS, TYPE_LABELS, VERDICT_LABELS } from '$lib/result/labels';
	import type { Confidence, Finding, Verdict } from '$lib/result/types';

	interface Props {
		/** The finding as shown: its confidence already capped (lib/analysis/confidence.ts). */
		finding: Finding;
		/** The employee's mark, if any. */
		verdict: Verdict | null;
		/** The card was clicked or activated from the keyboard: open the evidence. */
		onopen: (findingId: string) => void;
	}

	let { finding, verdict, onopen }: Props = $props();

	const confidenceClass: Record<Confidence, string> = {
		high: 'bg-ok-soft text-ok',
		medium: 'bg-warn-soft text-warn',
		low: 'bg-bad-soft text-bad'
	};

	const title = $derived(cardTitle(finding));
	const evidence = $derived(finding.evidence);
</script>

<!-- A finding on the «Анализ» page (tech task §6.5); opens the same evidence panel as the visual. -->
<button
	type="button"
	class="grid w-full gap-1.5 rounded-lg border border-l-4 border-line border-l-(--c) bg-surface px-4 py-3 text-left transition hover:border-(--c)"
	style:--c={`var(--${finding.type})`}
	onclick={() => onopen(finding.id)}
>
	<span class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
		<span class="font-semibold text-(--c)">{TYPE_LABELS[finding.type]}</span>
		<span class="font-mono text-xs text-muted">{finding.id}</span>
		<span class="text-muted">· {finding.block}</span>
		{#if verdict}
			<span
				class={[
					'ml-auto rounded-full px-2 text-[11px] font-semibold',
					verdict === 'ok' ? 'bg-ok-soft text-ok' : 'bg-bad-soft text-bad'
				]}
			>
				{VERDICT_LABELS[verdict]}
			</span>
		{/if}
	</span>
	{#if title}
		<span class="block font-semibold text-balance">{title}</span>
	{/if}
	{#if finding.desc}
		<span class="block text-sm">{finding.desc}</span>
	{/if}
	<span class="block text-[13px] text-muted">
		Уверенность:
		<span
			class={[
				'rounded-full px-2 py-px text-xs font-semibold',
				confidenceClass[evidence.confidence]
			]}
		>
			{CONFIDENCE_LABELS[evidence.confidence]}
		</span>
		{#if evidence.confidence_note}
			— {evidence.confidence_note}
		{/if}
	</span>
</button>
