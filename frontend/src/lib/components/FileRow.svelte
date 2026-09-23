<script lang="ts">
	import { DOC_TYPES, DOC_TYPE_LABELS, isDocType } from '$lib/documents';
	import { extensionOf, formatSize } from '$lib/upload/files';
	import type { UploadItem, UploadSession } from '$lib/upload/session.svelte';

	interface Props {
		item: UploadItem;
		session: UploadSession;
	}

	let { item, session }: Props = $props();

	const selectId = $props.id();
	const format = $derived(extensionOf(item.file.name).slice(1).toUpperCase());
	const badgeClass = $derived(
		format === 'PDF'
			? 'bg-red-100 text-red-800'
			: format.startsWith('XLS')
				? 'bg-emerald-100 text-emerald-800'
				: 'bg-blue-100 text-blue-800'
	);

	function onTypeChange(event: Event & { currentTarget: HTMLSelectElement }) {
		const value = event.currentTarget.value;
		if (isDocType(value)) {
			void session.setType(item, value);
		}
	}
</script>

<li class="rounded-lg border border-slate-200 bg-white p-3">
	<div class="flex items-center gap-3">
		<span
			class={['w-12 shrink-0 rounded px-1.5 py-1 text-center text-xs font-semibold', badgeClass]}
		>
			{format}
		</span>
		<div class="min-w-0 flex-1">
			<p class="truncate text-sm font-medium" title={item.file.name}>{item.file.name}</p>
			<p class="text-xs text-slate-500">
				{formatSize(item.file.size)}
				{#if item.document}
					· распознано пунктов: {item.document.clause_count}
				{/if}
			</p>
		</div>
		<button
			type="button"
			class="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
			disabled={item.inFlight || item.busy}
			aria-label={`Удалить ${item.file.name}`}
			onclick={() => session.remove(item)}
		>
			<svg viewBox="0 0 20 20" fill="currentColor" class="size-5" aria-hidden="true">
				<path
					d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z"
				/>
			</svg>
		</button>
	</div>

	{#if item.document}
		<div class="mt-2 flex items-center gap-2">
			<label for={selectId} class="text-xs text-slate-500">Тип документа</label>
			<select
				id={selectId}
				class="min-w-0 flex-1 rounded border border-slate-300 bg-white px-2 py-1 text-sm disabled:opacity-60"
				value={item.document.doc_type}
				disabled={item.busy}
				onchange={onTypeChange}
			>
				{#each DOC_TYPES as type (type)}
					<option value={type}>{DOC_TYPE_LABELS[type]}</option>
				{/each}
			</select>
		</div>
	{/if}

	{#if item.status === 'uploading'}
		<progress class="mt-2 h-1.5 w-full" max="1" value={item.progress} aria-label="Загрузка файла"
		></progress>
		<p class="text-xs text-slate-500">Загрузка… {Math.round(item.progress * 100)}%</p>
	{:else if item.status === 'processing'}
		<progress class="mt-2 h-1.5 w-full" aria-label="Разбор документа"></progress>
		<p class="text-xs text-slate-500">Разбор документа…</p>
	{/if}

	{#if item.error}
		<div class="mt-2 flex items-start gap-2 text-sm text-red-700" role="alert">
			<p class="flex-1">{item.error}</p>
			{#if item.status === 'failed' && item.retriable}
				<button
					type="button"
					class="shrink-0 rounded border border-red-300 px-2 py-0.5 text-xs font-medium hover:bg-red-50"
					onclick={() => session.retry(item)}
				>
					Повторить
				</button>
			{/if}
		</div>
	{/if}
</li>
