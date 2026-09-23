<script lang="ts">
	import type { Attachment } from 'svelte/attachments';

	import type { AgentLogEntry } from '$lib/api/analyses';
	import { logTime } from '$lib/status/analysis-stages';

	interface Props {
		/** Steps of the agent, oldest first. */
		entries: readonly AgentLogEntry[];
	}

	let { entries }: Props = $props();
	const uid = $props.id();
	const headingId = `${uid}-heading`;

	/** While paused the list stays where the reader left it, even as new steps arrive. */
	let paused = $state(false);

	/** Keeps the newest step in view: re-runs on every new step and on «Продолжить прокрутку». */
	const followNewest: Attachment<HTMLElement> = (list) => {
		if (entries.length > 0 && !paused) {
			list.scrollTop = list.scrollHeight;
		}
	};
</script>

<section class="grid gap-2" aria-labelledby={headingId}>
	<div class="flex items-center justify-between gap-3">
		<h2 id={headingId} class="text-sm font-semibold">Журнал агента</h2>
		<button
			type="button"
			class="rounded border border-line px-2 py-0.5 text-xs font-medium hover:bg-accent-soft"
			onclick={() => (paused = !paused)}
		>
			{paused ? 'Продолжить прокрутку' : 'Пауза'}
		</button>
	</div>
	<!-- Not a live region: announcing every step would drown a screen reader. -->
	<ol
		class="grid max-h-64 content-start gap-1 overflow-y-auto rounded-lg border border-line bg-surface px-3 py-2 font-mono text-xs"
		{@attach followNewest}
	>
		<!-- Steps only ever get appended and hold no state, so their position identifies them. -->
		{#each entries as entry, index (index)}
			<li class="flex gap-3">
				<time datetime={entry.at} class="shrink-0 text-muted">{logTime(entry.at)}</time>
				<span class="break-words">{entry.message}</span>
			</li>
		{:else}
			<li class="text-muted">Агент ещё не сообщил о шагах.</li>
		{/each}
	</ol>
</section>
