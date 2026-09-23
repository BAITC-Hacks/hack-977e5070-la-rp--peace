<script lang="ts">
	import { onDestroy } from 'svelte';

	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import {
		FINISHED,
		getComparison,
		startComparison,
		type ComparisonOut
	} from '$lib/api/comparisons';
	import ProcessingStatus from '$lib/components/status/ProcessingStatus.svelte';
	import { progressOf } from '$lib/status/from-upload';
	import { overallStatus } from '$lib/status/stages';
	import { uploadSession } from '$lib/upload/current';
	import { parsedDocuments } from '$lib/upload/parsed';

	/** How often the running analysis is polled. */
	const POLL_MS = 3000;

	const rows = $derived(uploadSession.items.map(progressOf));
	const failed = $derived(overallStatus(rows) === 'failed');

	let comparison = $state<ComparisonOut | null>(null);
	let analysisError = $state<string | null>(null);
	let startedAt = $state(0);
	let now = $state(Date.now());
	let timer: ReturnType<typeof setTimeout> | undefined;
	let ticker: ReturnType<typeof setInterval> | undefined;

	const elapsed = $derived(Math.max(0, Math.round((now - startedAt) / 1000)));

	onDestroy(() => {
		clearTimeout(timer);
		clearInterval(ticker);
	});

	/** Parsing is over: start the before → after analysis and follow it to the results. */
	async function startAnalysis() {
		const documents = parsedDocuments(uploadSession.items);
		const before = documents.filter((doc) => doc.set === 'before').map((doc) => doc.id);
		const after = documents.filter((doc) => doc.set === 'after').map((doc) => doc.id);
		if (before.length === 0 || after.length === 0) {
			const [first] = documents;
			if (first) {
				void goto(resolve('/documents/[id]', { id: String(first.id) }));
			}
			return;
		}
		startedAt = Date.now();
		ticker = setInterval(() => (now = Date.now()), 1000);
		try {
			comparison = await startComparison(before, after);
			await follow(comparison.id);
		} catch (cause) {
			analysisError = cause instanceof Error ? cause.message : String(cause);
			clearInterval(ticker);
		}
	}

	async function follow(id: number) {
		const current = await getComparison(id);
		comparison = current;
		if (current.status === 'failed') {
			analysisError = current.error ?? 'Анализ завершился с ошибкой';
			clearInterval(ticker);
			return;
		}
		if (FINISHED.includes(current.status)) {
			clearInterval(ticker);
			void goto(resolve('/analyses/[id]/changes', { id: String(id) }));
			return;
		}
		timer = setTimeout(() => {
			follow(id).catch((cause: unknown) => {
				analysisError = cause instanceof Error ? cause.message : String(cause);
				clearInterval(ticker);
			});
		}, POLL_MS);
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
		<ProcessingStatus {rows} ondone={startAnalysis} />
		{#if comparison !== null && analysisError === null}
			<div role="status" class="grid gap-2 rounded-lg border border-line bg-surface px-4 py-3">
				<p>
					<strong class="font-semibold">Анализ «до» → «после»</strong>
					<span class="text-muted">
						— {comparison.status === 'pending'
							? 'извлекаем подразделения и функции обоих документов'
							: 'сравниваем функции'} · {elapsed} с
					</span>
				</p>
				<progress class="h-1.5 w-full accent-accent" aria-label="Анализ документов"></progress>
			</div>
		{/if}
		{#if analysisError !== null}
			<p role="alert" class="rounded-lg border border-bad bg-bad-soft px-4 py-3 text-bad">
				Анализ не выполнен: {analysisError}
			</p>
		{/if}
		{#if failed || analysisError !== null}
			<a href={resolve('/')} class="justify-self-start text-accent hover:underline">
				← Вернуться к загрузке
			</a>
		{/if}
	</div>
{/if}
