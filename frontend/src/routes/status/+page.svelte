<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import ProcessingStatus from '$lib/components/status/ProcessingStatus.svelte';
	import { progressOf } from '$lib/status/from-upload';
	import { overallStatus } from '$lib/status/stages';
	import { uploadSession } from '$lib/upload/current';
	import { parsedDocuments } from '$lib/upload/parsed';

	const rows = $derived(uploadSession.items.map(progressOf));
	const failed = $derived(overallStatus(rows) === 'failed');

	/** Parsing is over: open the structure of the first document, «До» when there is one. */
	function openDocuments() {
		const [first] = parsedDocuments(uploadSession.items);
		if (first) {
			void goto(resolve('/documents/[id]', { id: String(first.id) }));
		}
	}
</script>

<svelte:head><title>Обработка документов — Анализ реорганизации</title></svelte:head>

{#if uploadSession.restoring}
	<p class="text-muted" role="status">Восстанавливаем документы…</p>
{:else if uploadSession.items.length === 0}
	<div class="grid justify-items-start gap-3">
		<h1 class="text-2xl font-semibold">Обработка документов</h1>
		<p class="text-muted">Документы не загружены.</p>
		<a href={resolve('/')} class="text-accent hover:underline">Загрузить документы</a>
	</div>
{:else}
	<div class="grid gap-4">
		<ProcessingStatus {rows} ondone={openDocuments} />
		<p role="note" class="rounded-md bg-warn-soft px-4 py-2.5 text-sm text-warn">
			Сравнение документов «до» и «после» бэкенд пока не выполняет: после разбора откроется
			структура документов.
		</p>
		{#if failed}
			<a href={resolve('/')} class="justify-self-start text-accent hover:underline">
				← Вернуться к загрузке
			</a>
		{/if}
	</div>
{/if}
