<script lang="ts">
	import { splitContext } from '$lib/source/highlight';
	import { SET_LABELS } from '$lib/source/label';
	import { formatLocation } from '$lib/source/location';
	import { QUOTE_NOT_FOUND_MESSAGE, type SourcePanelState } from '$lib/source/panel.svelte';

	interface Props {
		panel: SourcePanelState;
	}

	let { panel }: Props = $props();

	const headingId = $props.id();
	const source = $derived(panel.source);
	const parts = $derived(source && splitContext(source.context, source.start, source.end));
	const place = $derived(source && formatLocation(source.location));

	/** Element focused when the panel opened; focus goes back to it on close. */
	let opener: HTMLElement | null = null;

	/** Opens and closes the native modal dialog as the panel state says. */
	function syncModal(dialog: HTMLDialogElement) {
		if (panel.isOpen && !dialog.open) {
			opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
			dialog.showModal();
		} else if (!panel.isOpen && dialog.open) {
			dialog.close();
		}
	}

	/** Runs however the dialog was closed: Esc, «×» or the panel state. */
	function onClose() {
		panel.close();
		if (opener?.isConnected) {
			opener.focus();
		}
		opener = null;
	}

	/** ←/→ page through the sources wherever the focus is while the modal panel is open. */
	function onKeydown(event: KeyboardEvent) {
		if (!panel.isOpen || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
			return;
		}
		if (event.key === 'ArrowLeft') {
			event.preventDefault();
			void panel.prev();
		} else if (event.key === 'ArrowRight') {
			event.preventDefault();
			void panel.next();
		}
	}
</script>

<svelte:window onkeydown={onKeydown} />

<dialog
	{@attach syncModal}
	class="fixed inset-y-0 right-0 left-auto m-0 h-full max-h-none w-[min(560px,100%)] max-w-none overflow-y-auto border-l border-line bg-surface text-ink"
	aria-labelledby={headingId}
	onclose={onClose}
>
	{#if panel.isOpen}
		<div class="flex flex-col gap-5 px-6 pt-4 pb-10">
			<header class="flex items-center gap-2">
				{#if panel.targets.length > 1}
					<!-- aria-disabled, not disabled: a disabled button drops focus out of the panel. -->
					<nav class="flex items-center gap-1" aria-label="Источники вывода">
						<button
							type="button"
							class="rounded px-2 py-0.5 text-lg text-muted hover:bg-neutral-soft hover:text-ink aria-disabled:cursor-not-allowed aria-disabled:opacity-40"
							aria-label="Предыдущий источник"
							aria-disabled={!panel.hasPrev}
							onclick={() => panel.prev()}
						>
							←
						</button>
						<span class="text-sm text-muted tabular-nums">
							{panel.index + 1} из {panel.targets.length}
						</span>
						<button
							type="button"
							class="rounded px-2 py-0.5 text-lg text-muted hover:bg-neutral-soft hover:text-ink aria-disabled:cursor-not-allowed aria-disabled:opacity-40"
							aria-label="Следующий источник"
							aria-disabled={!panel.hasNext}
							onclick={() => panel.next()}
						>
							→
						</button>
					</nav>
				{/if}
				<button
					type="button"
					class="ml-auto rounded px-2 text-2xl leading-none text-muted hover:bg-neutral-soft hover:text-ink"
					aria-label="Закрыть"
					onclick={() => panel.close()}
				>
					×
				</button>
			</header>

			<h2 id={headingId} class="text-lg/snug font-semibold break-words">
				{source?.document_name ?? 'Источник'}
			</h2>

			{#if panel.status === 'loading'}
				<p class="text-sm text-muted" aria-live="polite">Загрузка источника…</p>
			{:else if panel.status === 'not_found'}
				<div class="rounded-md border border-warn bg-warn-soft p-3 text-sm text-warn" role="alert">
					<p class="font-medium">{QUOTE_NOT_FOUND_MESSAGE}</p>
					{#if panel.current?.quote}
						<p class="mt-1">Цитата в выводе: «{panel.current.quote}»</p>
					{/if}
				</div>
			{:else if panel.status === 'failed'}
				<div class="flex items-start gap-2 text-sm text-bad" role="alert">
					<p class="flex-1">{panel.error}</p>
					{#if panel.retriable}
						<button
							type="button"
							class="shrink-0 rounded border border-bad px-2 py-0.5 text-xs font-medium hover:bg-bad-soft"
							onclick={() => panel.retry()}
						>
							Повторить
						</button>
					{/if}
				</div>
			{:else if source && parts}
				<div class="flex flex-wrap items-center gap-2">
					{#if source.set}
						<span class="rounded bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent">
							{SET_LABELS[source.set]}
						</span>
					{/if}
					<span class="font-mono text-sm">{source.anchor}</span>
				</div>

				<dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
					<dt class="text-muted">Где искать</dt>
					<dd class="break-words">{source.path}</dd>
					{#if place}
						<dt class="text-muted">Место в файле</dt>
						<dd>{place}</dd>
					{/if}
				</dl>

				<section>
					<h3 class="mb-2 text-xs font-semibold tracking-wider text-muted uppercase">
						Цитата в контексте
					</h3>
					<blockquote
						class="rounded-md border border-line bg-page p-3 text-sm break-words whitespace-pre-wrap"
					>
						{parts.before}<mark class="rounded-sm bg-hl text-ink">{parts.quote}</mark>{parts.after}
					</blockquote>
				</section>

				<a
					class="self-start rounded-md border border-line px-3 py-1.5 text-sm font-medium text-accent hover:bg-accent-soft"
					href={panel.downloadUrl}
					rel="external"
					download={source.document_name}
				>
					Скачать оригинал
				</a>
			{/if}
		</div>
	{/if}
</dialog>
