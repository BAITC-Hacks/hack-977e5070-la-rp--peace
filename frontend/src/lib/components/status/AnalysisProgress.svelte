<script lang="ts">
	import type { Attachment } from 'svelte/attachments';

	import type { AnalysisRun } from '$lib/status/analysis-run.svelte';
	import { stageState } from '$lib/status/analysis-stages';

	import AgentLog from './AgentLog.svelte';
	import StageCell from './StageCell.svelte';

	interface Props {
		run: AnalysisRun;
		/**
		 * Called once the final notice has been on screen for a moment: the run is done, or the
		 * server does not run analyses yet.
		 */
		onopen: () => void;
		/** What `onopen` opens once the run is done, e.g. «Открываю изменения…». */
		doneText: string;
		/** What `onopen` opens when the server does not run analyses. */
		unavailableText: string;
	}

	let { run, onopen, doneText, unavailableText }: Props = $props();
	const uid = $props.id();
	const headingId = `${uid}-heading`;

	/** How long the final notice stays on screen before `onopen`, as on the parsing table. */
	const OPEN_DELAY_MS = 1200;

	/** Calls `onopen` after OPEN_DELAY_MS; leaving the screen before that cancels the call. */
	const openLater: Attachment = () => {
		const timer = setTimeout(onopen, OPEN_DELAY_MS);
		return () => clearTimeout(timer);
	};
</script>

<section class="grid gap-4" aria-labelledby={headingId}>
	<h2 id={headingId} class="text-xl font-semibold">Анализ документов</h2>

	<ol class="grid gap-1.5 rounded-lg border border-line bg-surface px-4 py-3">
		{#each run.stages as stage (stage.name)}
			<li class="flex items-center justify-between gap-4">
				<span>{stage.name}</span>
				<StageCell state={stageState(stage.status)} />
			</li>
		{/each}
	</ol>

	{#if run.polling && run.phase === 'running'}
		<p role="status" class="text-sm text-muted">
			Поток событий прервался: статус обновляется раз в 2 секунды.
		</p>
	{/if}

	{#if run.phase === 'running' || run.phase === 'starting'}
		<div class="grid justify-items-start gap-1">
			<button
				type="button"
				class="rounded border border-line px-3 py-1.5 text-sm font-medium hover:bg-bad-soft disabled:cursor-not-allowed disabled:opacity-50"
				disabled={run.phase !== 'running' || run.cancelling}
				onclick={() => run.cancel()}
			>
				{run.cancelling ? 'Отменяю…' : 'Отменить'}
			</button>
			{#if run.cancelError}
				<p role="alert" class="text-sm text-bad">Не удалось отменить: {run.cancelError}</p>
			{/if}
		</div>
	{:else if run.phase === 'failed'}
		<div
			role="alert"
			class="flex items-start gap-3 rounded-lg border border-bad bg-bad-soft px-4 py-3 text-bad"
		>
			<div class="grid flex-1 gap-1">
				<p class="font-semibold">Анализ завершился с ошибкой</p>
				<p>{run.error}</p>
			</div>
			<button
				type="button"
				class="shrink-0 rounded border border-bad px-3 py-1.5 text-sm font-medium hover:bg-surface"
				onclick={() => run.retry()}
			>
				Повторить
			</button>
		</div>
	{:else if run.phase === 'cancelled'}
		<div class="flex items-center gap-3">
			<p role="status" class="text-muted">Анализ отменён.</p>
			<button
				type="button"
				class="rounded border border-line px-3 py-1.5 text-sm font-medium hover:bg-accent-soft"
				onclick={() => run.retry()}
			>
				Запустить заново
			</button>
		</div>
	{:else if run.phase === 'unavailable'}
		<p role="status" class="rounded-md bg-warn-soft px-4 py-2.5 text-warn" {@attach openLater}>
			<strong class="font-semibold">{run.error}.</strong>
			{unavailableText}
		</p>
	{:else if run.phase === 'done'}
		<p role="status" {@attach openLater}>
			<strong class="font-semibold">Готово.</strong>
			<span class="text-muted">{doneText}</span>
		</p>
	{/if}

	<AgentLog entries={run.log} />
</section>
