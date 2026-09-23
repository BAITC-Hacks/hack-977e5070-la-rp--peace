<script lang="ts">
	import type { Attachment } from 'svelte/attachments';

	import '$lib/result/colors.css';
	import { findingsOfItem, focusOf } from '$lib/result/derive';
	import { DOC_LABELS, LOSS_MARK } from '$lib/result/labels';
	import type { ReviewState } from '$lib/result/review.svelte';
	import type { Block, BlockItem, Finding } from '$lib/result/types';
	import { type RowLayout, layoutArrows } from '$lib/visual/arrows';
	import { measureRow } from '$lib/visual/measure';

	import ChangeCard from './ChangeCard.svelte';
	import StatusBadge from './StatusBadge.svelte';

	interface Props {
		block: Block;
		/** The block's findings that may be shown (`blockFindings`), in display order. */
		findings: Finding[];
		review: ReviewState;
		onopen: (findingId: string) => void;
	}

	let { block, findings, review, onopen }: Props = $props();

	const uid = $props.id();
	let layout = $state.raw<RowLayout | null>(null);
	/** Findings under the pointer or keyboard focus. */
	let focused = $state.raw<string[]>([]);

	const drawn = $derived(
		layout === null ? { arrows: [], marks: [] } : layoutArrows(findings, layout)
	);
	const lit = $derived(focusOf(findings, focused));
	const focusing = $derived(lit.findings.size > 0);
	const types = $derived([...new Set(findings.map((finding) => finding.type))]);

	// Arrows follow the boxes: a size change of the row, a column, a card or an item re-measures.
	let row: HTMLElement | null = null;
	const observer = new ResizeObserver(remeasure);

	function remeasure() {
		if (row !== null) {
			layout = measureRow(row);
		}
	}

	const watchRow: Attachment<HTMLElement> = (element) => {
		row = element;
		observer.observe(element);
		// Text metrics change once the web fonts are in.
		void document.fonts.ready.then(remeasure);
		return () => {
			observer.disconnect();
			row = null;
		};
	};

	const watch: Attachment<HTMLElement> = (element) => {
		observer.observe(element);
		return () => observer.unobserve(element);
	};

	function hoverItem(item: BlockItem, active: boolean) {
		focused = active ? findingsOfItem(findings, item.id) : [];
	}
</script>

{#snippet entry(item: BlockItem)}
	{@const on = lit.items.has(item.id)}
	<li
		data-item={item.id}
		class={[
			'flex items-center justify-between gap-2.5 rounded-md px-2.5 py-2 transition',
			on && 'bg-neutral-soft',
			focusing && !on && 'opacity-35'
		]}
		onpointerenter={() => hoverItem(item, true)}
		onpointerleave={() => hoverItem(item, false)}
		{@attach watch}
	>
		<span>{item.label}</span>
		{#if item.status}
			<StatusBadge status={item.status} />
		{/if}
	</li>
{/snippet}

<section class="grid gap-2.5" aria-labelledby="{uid}-title">
	<h2 id="{uid}-title" class="mt-5 font-semibold">{block.title}</h2>
	<div
		class="relative grid grid-cols-[1fr_minmax(240px,300px)_1fr] items-start gap-x-12"
		{@attach watchRow}
	>
		<ul
			data-column="before"
			aria-label={DOC_LABELS.before}
			class="rounded-lg border border-line bg-surface px-2 py-2.5"
			{@attach watch}
		>
			{#each block.before as item (item.id)}
				{@render entry(item)}
			{/each}
		</ul>

		<ul aria-label="Изменения" class="flex flex-col gap-2.5" {@attach watch}>
			{#each findings as finding (finding.id)}
				<li data-finding={finding.id} {@attach watch}>
					<ChangeCard
						{finding}
						verdict={review.verdictOf(finding.id)}
						lit={lit.findings.has(finding.id)}
						dimmed={focusing && !lit.findings.has(finding.id)}
						{onopen}
						onhover={(active) => (focused = active ? [finding.id] : [])}
					/>
				</li>
			{/each}
		</ul>

		<ul
			data-column="after"
			aria-label={DOC_LABELS.after}
			class="rounded-lg border border-accent bg-surface px-2 py-2.5"
			{@attach watch}
		>
			{#each block.after as item (item.id)}
				{@render entry(item)}
			{/each}
		</ul>

		<!-- Arrows run only through the gaps between the columns, so the layer can sit on top. -->
		<svg
			class="pointer-events-none absolute inset-0 z-10 size-full overflow-visible"
			aria-hidden="true"
		>
			<defs>
				{#each types as type (type)}
					<marker
						id="{uid}-{type}"
						viewBox="0 0 10 10"
						refX="9"
						refY="5"
						markerWidth="7"
						markerHeight="7"
						orient="auto-start-reverse"
					>
						<path d="M0,0 L10,5 L0,10 z" style:fill={`var(--${type})`} />
					</marker>
				{/each}
			</defs>
			{#each drawn.arrows as arrow (arrow.key)}
				<path
					d={arrow.d}
					data-arrow={arrow.key}
					fill="none"
					stroke-width={arrow.width}
					stroke-dasharray={arrow.dash}
					marker-end={arrow.head ? `url(#${uid}-${arrow.type})` : undefined}
					class={[
						'transition-opacity',
						focusing && !lit.findings.has(arrow.finding) && 'opacity-10'
					]}
					style:stroke={`var(--${arrow.type})`}
				/>
			{/each}
			<!-- The label may reach into the «после» column; the halo keeps it readable there. -->
			{#each drawn.marks as mark (mark.finding)}
				<text
					x={mark.x}
					y={mark.y}
					paint-order="stroke"
					stroke-width="4"
					stroke-linejoin="round"
					class={[
						'text-[13px] font-semibold transition-opacity',
						focusing && !lit.findings.has(mark.finding) && 'opacity-10'
					]}
					style:fill="var(--loss)"
					style:stroke="var(--surface)"
				>
					{LOSS_MARK}
				</text>
			{/each}
		</svg>
	</div>
</section>
