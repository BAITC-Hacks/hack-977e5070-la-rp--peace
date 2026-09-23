<script lang="ts">
	import { untrack } from 'svelte';

	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { documentApi } from '$lib/api/document';
	import WordDiff from '$lib/components/diff/WordDiff.svelte';
	import { CompareView } from '$lib/diff/view.svelte';

	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const view = $derived(new CompareView(documentApi, data.before, data.after));

	// Network requests and the 2 s poll; new ids get a new view and the old one stops.
	$effect(() => {
		const current = view;
		untrack(() => current.start());
		return () => current.stop();
	});
</script>

<svelte:head>
	<title>Изменения → Word — Анализ реорганизации</title>
</svelte:head>

<div class="grid gap-5">
	<header class="flex flex-wrap items-end gap-x-4 gap-y-2">
		<div class="grid gap-1">
			<p class="text-xs font-medium tracking-[0.07em] text-muted uppercase">Изменения</p>
			<h1 class="text-2xl font-semibold">Сравнение текстов «До» и «После»</h1>
		</div>
		{#if view.status === 'ready'}
			<button
				type="button"
				data-print="hide"
				class="ml-auto rounded-md border border-line bg-page px-2.5 py-1 text-[13px] font-medium text-accent hover:border-accent"
				onclick={() => window.print()}
			>
				Скачать PDF
			</button>
		{/if}
	</header>

	{#if view.status === 'missing' || view.status === 'same'}
		<div class="grid gap-1.5 rounded-lg border border-line bg-surface p-6">
			<p class="font-medium">
				{view.status === 'same'
					? 'Для сравнения нужны два разных документа.'
					: 'Не выбраны документы для сравнения.'}
			</p>
			<p class="text-muted">
				Загрузите документы «До» и «После» и откройте сравнение из анализа.
				<a href={resolve('/')} class="text-accent hover:underline">К загрузке</a>
			</p>
		</div>
	{:else if view.status === 'failed'}
		<div
			class="flex items-start gap-3 rounded-md border border-bad bg-bad-soft p-3 text-bad"
			role="alert"
		>
			<div class="grid flex-1 gap-2">
				<p>{view.error}</p>
				<div class="flex flex-wrap gap-x-4 gap-y-1 text-sm">
					{#if view.beforeId !== null}
						<a
							href={resolve('/documents/[id]', { id: String(view.beforeId) })}
							class="underline underline-offset-2"
						>
							Открыть документ «До»
						</a>
					{/if}
					{#if view.afterId !== null}
						<a
							href={resolve('/documents/[id]', { id: String(view.afterId) })}
							class="underline underline-offset-2"
						>
							Открыть документ «После»
						</a>
					{/if}
				</div>
			</div>
			<button
				type="button"
				class="shrink-0 rounded border border-bad px-2 py-0.5 text-sm font-medium hover:bg-surface"
				onclick={() => view.retry()}
			>
				Повторить
			</button>
		</div>
	{:else if view.status === 'pending'}
		<div class="grid gap-1 rounded-lg border border-line bg-surface p-4" role="status">
			<p class="font-medium">Документ ещё разбирается</p>
			<p class="text-sm text-muted">
				Сравнение откроется само, как только разбор закончится. Проверяем каждые 2 секунды.
			</p>
			<progress class="mt-2 h-1.5 w-full accent-accent" aria-label="Разбор документов"></progress>
		</div>
	{:else if view.status === 'ready' && view.before && view.after}
		<WordDiff before={view.before} after={view.after} hash={page.url.hash} />
	{:else}
		<div class="grid animate-pulse gap-3" aria-hidden="true">
			<div class="grid grid-cols-2 gap-3">
				<div class="h-16 rounded-lg bg-neutral-soft"></div>
				<div class="h-16 rounded-lg bg-neutral-soft"></div>
			</div>
			<div class="h-4 w-1/2 rounded bg-neutral-soft"></div>
			<div class="h-48 rounded-lg bg-neutral-soft"></div>
		</div>
		<span class="sr-only" role="status">Загрузка документов…</span>
	{/if}
</div>
