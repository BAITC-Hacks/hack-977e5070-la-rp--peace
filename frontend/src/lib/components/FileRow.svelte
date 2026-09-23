<script lang="ts">
	import { resolve } from '$app/paths';
	import type { Pathname } from '$app/types';
	import { DOC_TYPE_SUGGESTIONS } from '$lib/documents';
	import { extensionOf, formatSize } from '$lib/upload/files';
	import type { UploadItem, UploadSession } from '$lib/upload/session.svelte';

	interface Props {
		item: UploadItem;
		session: UploadSession;
	}

	let { item, session }: Props = $props();

	const uid = $props.id();
	const format = $derived(
		(item.document?.source_format ?? extensionOf(item.file.name).slice(1)).toUpperCase()
	);
	const badgeClass = $derived(
		format === 'PDF'
			? 'bg-bad-soft text-bad'
			: format.startsWith('XLS')
				? 'bg-ok-soft text-ok'
				: 'bg-accent-soft text-accent'
	);
	const statusClass = $derived(
		item.status === 'parsed'
			? 'text-ok'
			: item.status === 'needs_review'
				? 'text-warn'
				: item.status === 'failed'
					? 'text-bad'
					: 'text-muted'
	);

	async function onTypeChange(event: Event & { currentTarget: HTMLInputElement }) {
		const input = event.currentTarget;
		await session.setType(item, input.value);
		// Show what is stored: the trimmed value, or the previous one if the edit was empty or refused.
		input.value = item.document?.document_type ?? '';
	}
</script>

<li class="rounded-md border border-line bg-surface p-3">
	<div class="flex items-center gap-3">
		<span
			class={[
				'w-12 shrink-0 rounded px-1.5 py-1 text-center font-mono text-xs font-medium',
				badgeClass
			]}
		>
			{format}
		</span>
		<div class="min-w-0 flex-1">
			<p class="truncate text-sm font-medium" title={item.file.name}>{item.file.name}</p>
			<p class="text-xs text-muted">
				{formatSize(item.file.size)} ·
				<span class={['font-medium', statusClass]}>{item.statusLabel}</span>
			</p>
		</div>
		<button
			type="button"
			class="rounded p-1 text-muted hover:bg-neutral-soft hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
			disabled={!item.removable}
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

	{#if item.status === 'uploading'}
		<progress
			class="mt-2 h-1.5 w-full accent-accent"
			max="1"
			value={item.progress}
			aria-label="Загрузка файла"
		></progress>
	{:else if item.status === 'parsing'}
		<progress class="mt-2 h-1.5 w-full accent-accent" aria-label="Разбор документа"></progress>
	{/if}

	{#if item.status === 'needs_review' && item.document}
		<p class="mt-2 text-sm text-warn">
			Блокирующих проблем: {item.document.blocking_issues}, прочих: {item.document.other_issues}
		</p>
	{/if}

	{#if item.parsed && item.document}
		<div class="mt-2 flex flex-wrap items-center gap-2">
			<label for={`${uid}-type`} class="text-xs text-muted">Тип документа</label>
			<input
				id={`${uid}-type`}
				list={`${uid}-types`}
				class="min-w-40 flex-1 rounded-md border border-line bg-page px-2 py-1 text-sm disabled:opacity-60"
				value={item.document.document_type ?? ''}
				placeholder="Не определён"
				aria-describedby={`${uid}-type-hint`}
				disabled={item.busy}
				onchange={onTypeChange}
			/>
			<datalist id={`${uid}-types`}>
				{#each DOC_TYPE_SUGGESTIONS as type (type)}
					<option value={type}></option>
				{/each}
			</datalist>
			<!-- routes/documents/[id] is built in parallel; the cast goes once the route exists. -->
			<a
				href={resolve(`/documents/${item.document.id}` as Pathname)}
				class="text-sm font-medium text-accent underline underline-offset-2"
			>
				Открыть структуру
			</a>
		</div>
		<p id={`${uid}-type-hint`} class="mt-1 text-xs text-muted">
			{item.document.document_type === null
				? 'В документе тип не найден — выберите из списка или впишите свой.'
				: 'Если тип неверный, выберите другой из списка или впишите свой.'}
		</p>
	{/if}

	{#if item.error}
		<div class="mt-2 flex items-start gap-2 text-sm text-bad" role="alert">
			<p class="min-w-0 flex-1 wrap-anywhere">{item.error}</p>
			{#if item.status === 'failed' && item.retriable}
				<button
					type="button"
					class="shrink-0 rounded border border-bad px-2 py-0.5 text-xs font-medium hover:bg-bad-soft"
					onclick={() => session.retry(item)}
				>
					Повторить
				</button>
			{/if}
		</div>
	{/if}
</li>
