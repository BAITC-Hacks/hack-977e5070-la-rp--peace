<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import AnalysisProgress from '$lib/components/status/AnalysisProgress.svelte';
	import ProcessingStatus from '$lib/components/status/ProcessingStatus.svelte';
	import { defaultAnalysisName } from '$lib/status/analysis-stages';
	import { analysisRun } from '$lib/status/current-run';
	import { progressOf } from '$lib/status/from-upload';
	import { overallStatus } from '$lib/status/stages';
	import { uploadSession } from '$lib/upload/current';
	import { parsedDocuments } from '$lib/upload/parsed';

	const rows = $derived(uploadSession.items.map(progressOf));
	const failed = $derived(overallStatus(rows) === 'failed');
	const documents = $derived(parsedDocuments(uploadSession.items));
	const documentIds = $derived(documents.map((document) => document.id));
	/** The run shown below the parsing table: only one over exactly these documents. */
	const runShown = $derived(analysisRun.phase !== 'idle' && analysisRun.isFor(documentIds));

	/** Parsing is over: start the analysis, unless it already runs over these documents. */
	function startAnalysis() {
		if (!runShown) {
			void analysisRun.start({ name: defaultAnalysisName(new Date()), documentIds });
		}
	}

	/**
	 * The analysis is over: open «Изменения» (tz_site.md §6.2). If the server does not run
	 * analyses yet, open the structure of the first document, «До» when there is one.
	 */
	function openResults() {
		const id = analysisRun.analysisId;
		if (analysisRun.phase === 'done' && id !== null) {
			void goto(resolve('/analyses/[id]/changes', { id: String(id) }));
			return;
		}
		const [first] = documents;
		if (first) {
			void goto(resolve('/documents/[id]', { id: String(first.id) }));
		}
	}
</script>

<svelte:head><title>Обработка документов — Анализ реорганизации</title></svelte:head>

{#if uploadSession.items.length === 0}
	<!-- The upload list lives in memory: after a reload there is nothing to follow. -->
	<div class="grid justify-items-start gap-3">
		<h1 class="text-2xl font-semibold">Обработка документов</h1>
		<p class="text-muted">Документы не загружены.</p>
		<a href={resolve('/')} class="text-accent hover:underline">Загрузить документы</a>
	</div>
{:else}
	<div class="grid gap-6">
		<ProcessingStatus
			{rows}
			ondone={startAnalysis}
			doneText="Документы разобраны. Запускаю анализ…"
		/>
		{#if runShown}
			<AnalysisProgress
				run={analysisRun}
				onopen={openResults}
				doneText="Открываю «Изменения»…"
				unavailableText="Открываю структуру документов…"
			/>
		{/if}
		{#if failed}
			<a href={resolve('/')} class="justify-self-start text-accent hover:underline">
				← Вернуться к загрузке
			</a>
		{/if}
	</div>
{/if}
