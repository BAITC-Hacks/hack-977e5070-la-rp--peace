<script lang="ts">
	import { untrack } from 'svelte';

	import { resolve } from '$app/paths';
	import { documentApi, fileUrl, type ParseStatus } from '$lib/api/document';
	import { sourcesApi } from '$lib/api/sources';
	import DocumentCard from '$lib/components/document/DocumentCard.svelte';
	import IssueList from '$lib/components/document/IssueList.svelte';
	import NodeTree from '$lib/components/document/NodeTree.svelte';
	import SourcePanel from '$lib/components/source/SourcePanel.svelte';
	import { DOC_SET_LABELS, PARSE_STATUS_LABELS } from '$lib/document/labels';
	import { TreeState } from '$lib/document/tree-state.svelte';
	import { DocumentView } from '$lib/document/view.svelte';
	import { SourcePanelState } from '$lib/source/panel.svelte';
	import { formatSize } from '$lib/upload/files';

	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const view = $derived(new DocumentView(documentApi, data.id));
	const tree = $derived(view.details && new TreeState(view.details.nodes));
	const panel = new SourcePanelState(sourcesApi);
	const anchors = $derived(new Map(view.details?.nodes.map((node) => [node.id, node.anchor])));

	const STATUS_CLASSES: Record<ParseStatus, string> = {
		pending: 'bg-neutral-soft text-neutral',
		parsed: 'bg-ok-soft text-ok',
		needs_review: 'bg-warn-soft text-warn',
		validated: 'bg-ok-soft text-ok'
	};

	// Network requests and the 2 s poll; a new id gets a new view and the old one stops.
	$effect(() => {
		const current = view;
		untrack(() => current.start());
		return () => current.stop();
	});
</script>

<svelte:head>
	<title>{view.document?.file_name ?? 'Документ'} — Анализ реорганизации</title>
</svelte:head>

{#snippet skeleton()}
	<div class="grid animate-pulse gap-2.5" aria-hidden="true">
		<div class="h-4 w-2/3 rounded bg-neutral-soft"></div>
		<div class="h-4 w-full rounded bg-neutral-soft"></div>
		<div class="h-4 w-5/6 rounded bg-neutral-soft"></div>
	</div>
{/snippet}

<div class="grid gap-5">
	<nav class="flex flex-wrap items-center justify-between gap-3">
		<a href={resolve('/')} class="text-sm text-accent hover:underline">← К загрузке</a>
		{#if view.document}
			<a
				href={fileUrl(view.document.id)}
				rel="external"
				download={view.document.file_name}
				class="rounded-md border border-accent px-3 py-1.5 text-sm font-semibold text-accent hover:bg-accent-soft"
			>
				Скачать оригинал
			</a>
		{/if}
	</nav>

	{#if view.status === 'not_found'}
		<div class="grid gap-1.5 rounded-lg border border-line bg-surface p-6">
			<h1 class="text-xl font-semibold">Документ не найден</h1>
			<p class="text-muted">Возможно, его удалили. Вернитесь к загрузке и добавьте файл заново.</p>
		</div>
	{:else}
		{#if view.document}
			{@const doc = view.document}
			<header class="grid gap-1.5">
				<p class="text-xs font-medium tracking-[0.07em] text-muted uppercase">
					{doc.set ? `Документ ${DOC_SET_LABELS[doc.set]}` : 'Документ'}
				</p>
				<h1 class="text-2xl font-semibold wrap-anywhere">{doc.file_name}</h1>
				<p class="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
					<span
						class={['rounded px-2 py-0.5 text-xs font-semibold', STATUS_CLASSES[doc.parse_status]]}
					>
						{PARSE_STATUS_LABELS[doc.parse_status]}
					</span>
					<span>{doc.source_format.toUpperCase()} · {formatSize(doc.file_size_bytes)}</span>
					{#if doc.parse_status !== 'pending'}
						<span>· узлов: {doc.node_count}</span>
					{/if}
				</p>
			</header>
		{:else if view.status === 'loading'}
			<div class="grid animate-pulse gap-2" aria-hidden="true">
				<div class="h-3 w-28 rounded bg-neutral-soft"></div>
				<div class="h-7 w-1/2 rounded bg-neutral-soft"></div>
				<div class="h-4 w-60 rounded bg-neutral-soft"></div>
			</div>
		{/if}

		{#if view.status === 'failed'}
			<div
				class="flex items-start gap-3 rounded-md border border-bad bg-bad-soft p-3 text-bad"
				role="alert"
			>
				<p class="flex-1">{view.error}</p>
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
					Страница обновится сама, как только разбор закончится. Проверяем каждые 2 секунды.
				</p>
				<progress class="mt-2 h-1.5 w-full accent-accent" aria-label="Разбор документа"></progress>
			</div>
		{:else}
			{@const details = view.details}
			<span class="sr-only" role="status">{details ? '' : 'Загрузка документа…'}</span>

			<section
				class="grid gap-3 rounded-lg border border-line bg-surface p-4"
				aria-labelledby="card-heading"
			>
				<h2 id="card-heading" class="text-lg font-semibold">Реквизиты</h2>
				{#if details && view.document}
					<DocumentCard card={view.document} evidence={details.profile.metadata_evidence} />
				{:else}
					{@render skeleton()}
				{/if}
			</section>

			<section
				class="grid gap-3 rounded-lg border border-line bg-surface p-4"
				aria-labelledby="issues-heading"
			>
				<h2 id="issues-heading" class="text-lg font-semibold">
					Проблемы разбора
					{#if details && details.issues.length > 0}
						<span class="font-normal text-muted">· {details.issues.length}</span>
					{/if}
				</h2>
				{#if details}
					<IssueList
						issues={details.issues}
						{anchors}
						onreveal={(nodeId) => tree?.reveal(nodeId)}
					/>
				{:else}
					{@render skeleton()}
				{/if}
			</section>

			<section
				class="grid gap-3 rounded-lg border border-line bg-surface p-4"
				aria-labelledby="tree-heading"
			>
				<h2 id="tree-heading" class="text-lg font-semibold">Структура документа</h2>
				{#if tree}
					<NodeTree {tree} onopen={(nodeId) => panel.open([{ nodeId }])} />
				{:else}
					{@render skeleton()}
				{/if}
			</section>
		{/if}
	{/if}
</div>

<SourcePanel {panel} />
