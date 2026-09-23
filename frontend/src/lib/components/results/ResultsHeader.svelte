<script lang="ts">
	import { resolve } from '$app/paths';
	import { DISCLAIMER } from '$lib/result/labels';

	import { RESULTS_SECTIONS, type ResultsSectionId } from './sections';

	interface Props {
		/** Analysis whose results are shown. */
		id: string;
		/** Section on screen; none is marked for any other page. */
		current: ResultsSectionId | null;
	}

	let { id, current }: Props = $props();
</script>

<!-- Menu of the results screens (tz_site.md §6) and the disclaimer every one of them shows (I6). -->
<div class="grid gap-3">
	<nav aria-label="Разделы результата" class="flex flex-wrap gap-1 border-b border-line">
		{#each RESULTS_SECTIONS as section (section.id)}
			{#if section.enabled}
				<a
					href={section.id === 'analysis'
						? resolve('/analyses/[id]/analysis', { id })
						: resolve('/analyses/[id]/changes', { id })}
					aria-current={section.id === current ? 'page' : undefined}
					class={[
						'-mb-px border-b-2 px-2.5 pt-2 pb-2.5 font-medium',
						section.id === current
							? 'border-accent text-ink'
							: 'border-transparent text-muted hover:text-ink'
					]}
				>
					{section.label}
				</a>
			{:else}
				<span
					role="link"
					aria-disabled="true"
					class="-mb-px cursor-not-allowed border-b-2 border-transparent px-2.5 pt-2 pb-2.5 font-medium text-muted opacity-60"
				>
					{section.label}
				</span>
			{/if}
		{/each}
	</nav>

	<p role="note" class="rounded-md bg-warn-soft px-3 py-1.5 text-sm text-warn">{DISCLAIMER}</p>
</div>
