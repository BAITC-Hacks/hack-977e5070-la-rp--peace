<script lang="ts">
	import { withShownConfidence } from '$lib/analysis/confidence';
	import { ANALYSIS_TABS, tabAfterKey, tabFindings, type AnalysisTabId } from '$lib/analysis/tabs';
	import EvidenceDrawer from '$lib/components/evidence/EvidenceDrawer.svelte';
	import { visibleFindings } from '$lib/result/derive';
	import type { ReviewState } from '$lib/result/review.svelte';
	import type { JobResult, Source } from '$lib/result/types';

	import FindingCard from './FindingCard.svelte';

	interface Props {
		result: JobResult;
		review: ReviewState;
		/** A quote in the evidence panel was clicked; the panel is already closed. */
		onquote: (source: Source) => void;
		/** The open sub-page; bind it to keep it in the URL. */
		tab?: AnalysisTabId;
	}

	let { result, review, onquote, tab = $bindable('loss') }: Props = $props();

	const uid = $props.id();

	/** Sub-pages with their findings: only sourced ones (I1), confidence capped (P1.5). */
	const tabs = $derived.by(() => {
		const shown = visibleFindings(result).map(withShownConfidence);
		return ANALYSIS_TABS.map((item) => ({ ...item, findings: tabFindings(shown, item) }));
	});

	let openId = $state<string | null>(null);
	const opened = $derived(
		openId === null
			? null
			: (tabs.flatMap((item) => item.findings).find((finding) => finding.id === openId) ?? null)
	);

	const tabId = (id: AnalysisTabId) => `${uid}-tab-${id}`;
	const panelId = (id: AnalysisTabId) => `${uid}-panel-${id}`;

	function select(index: number) {
		tab = tabs[index].id;
	}

	function move(event: KeyboardEvent, index: number) {
		const next = tabAfterKey(event.key, index, tabs.length);
		if (next === null) {
			return;
		}
		event.preventDefault();
		select(next);
		document.getElementById(tabId(tabs[next].id))?.focus();
	}

	function showQuote(source: Source) {
		openId = null;
		onquote(source);
	}
</script>

<!-- «Анализ» (tech task §6.5, P1.1): one sub-page per kind of problem, cards open the evidence. -->
<div class="grid gap-4">
	<div role="tablist" aria-label="Подразделы анализа" class="flex flex-wrap gap-1.5">
		{#each tabs as item, index (item.id)}
			{@const selected = item.id === tab}
			<button
				type="button"
				role="tab"
				id={tabId(item.id)}
				aria-selected={selected}
				aria-controls={panelId(item.id)}
				tabindex={selected ? 0 : -1}
				class={[
					'flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm',
					selected
						? 'border-accent bg-accent text-accent-ink'
						: 'border-line bg-surface text-ink hover:border-muted'
				]}
				onclick={() => select(index)}
				onkeydown={(event) => move(event, index)}
			>
				{item.label}
				<span
					class={[
						'min-w-5 rounded-full px-1.5 text-center text-xs font-semibold tabular-nums',
						selected ? 'bg-accent-ink text-accent' : 'bg-neutral-soft text-neutral'
					]}
				>
					{item.findings.length}
				</span>
			</button>
		{/each}
	</div>

	{#each tabs as item (item.id)}
		<div
			role="tabpanel"
			id={panelId(item.id)}
			aria-labelledby={tabId(item.id)}
			tabindex="0"
			hidden={item.id !== tab}
		>
			{#if item.findings.length > 0}
				<ul class="grid gap-3">
					{#each item.findings as finding (finding.id)}
						<li>
							<FindingCard
								{finding}
								verdict={review.verdictOf(finding.id)}
								onopen={(id) => (openId = id)}
							/>
						</li>
					{/each}
				</ul>
			{:else}
				<p
					class="rounded-lg border border-dashed border-line bg-surface px-4 py-6 text-center text-muted"
				>
					{item.empty}
				</p>
			{/if}
		</div>
	{/each}
</div>

<EvidenceDrawer finding={opened} {review} onclose={() => (openId = null)} onquote={showQuote} />
