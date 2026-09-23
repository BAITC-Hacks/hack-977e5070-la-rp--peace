<script lang="ts">
	import '$lib/result/colors.css';
	import { findingSources } from '$lib/result/derive';
	import { TYPE_LABELS, VERDICT_LABELS } from '$lib/result/labels';
	import type { Finding, Verdict } from '$lib/result/types';

	interface Props {
		finding: Finding;
		verdict: Verdict | null;
		/** Part of the hovered or focused link. */
		lit: boolean;
		/** Something else is in focus. */
		dimmed: boolean;
		onopen: (findingId: string) => void;
		/** Pointer or keyboard focus entered (true) or left (false) the card. */
		onhover: (active: boolean) => void;
	}

	let { finding, verdict, lit, dimmed, onopen, onhover }: Props = $props();

	/** Unchanged units and functions get a one-line card (visual_compare.html `compact`). */
	const compact = $derived(finding.type === 'kept');
	const sourceCount = $derived(findingSources(finding).length);
</script>

<button
	type="button"
	class={[
		'block w-full rounded-lg border border-l-4 bg-surface px-3 text-left transition',
		compact ? 'py-1.5' : 'py-2.5',
		lit ? 'translate-x-0.5 border-(--c)' : 'border-line border-l-(--c)',
		dimmed && 'opacity-35'
	]}
	style:--c={`var(--${finding.type})`}
	onclick={() => onopen(finding.id)}
	onpointerenter={() => onhover(true)}
	onpointerleave={() => onhover(false)}
	onfocus={() => onhover(true)}
	onblur={() => onhover(false)}
>
	<span class="flex items-center justify-between gap-2 text-[13px] font-semibold text-(--c)">
		<span>{finding.title || TYPE_LABELS[finding.type]}</span>
		{#if verdict}
			<span
				class={[
					'shrink-0 rounded-full px-2 text-[11px]',
					verdict === 'ok' ? 'bg-ok-soft text-ok' : 'bg-bad-soft text-bad'
				]}
			>
				{VERDICT_LABELS[verdict]}
			</span>
		{/if}
	</span>
	{#if !compact}
		{#if finding.desc}
			<span class="mt-0.5 block text-[13px]">{finding.desc}</span>
		{/if}
		<span class="mt-1 block text-xs text-muted">{finding.id} · источников: {sourceCount}</span>
	{/if}
</button>
