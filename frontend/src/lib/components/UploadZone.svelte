<script lang="ts">
	import type { DocSetInfo } from '$lib/documents';
	import { ACCEPTED_EXTENSIONS, ACCEPT_ATTRIBUTE } from '$lib/upload/files';
	import type { UploadSession } from '$lib/upload/session.svelte';

	import FileRow from './FileRow.svelte';

	interface Props {
		session: UploadSession;
		info: DocSetInfo;
	}

	let { session, info }: Props = $props();

	const headingId = $props.id();
	const items = $derived(session.itemsIn(info.set));
	/** A required set holds exactly one document; the optional ones take any number. */
	const single = $derived(!info.optional);
	const accepting = $derived(!single || items.length === 0);

	// dragenter/dragleave also fire for child elements, so count them instead of toggling a flag.
	let dragDepth = $state(0);
	let message = $state<string | null>(null);
	/** A file was dropped on a zone that already holds its one document; hidden once it is freed. */
	let refused = $state(false);

	function addFiles(files: FileList | null | undefined) {
		if (!files || files.length === 0) {
			return;
		}
		if (!accepting) {
			refused = true;
			return;
		}
		refused = false;
		if (single && files.length > 1) {
			message = 'Нужен один файл — перетащите только его.';
			return;
		}
		const rejected = session.add(info.set, files);
		message =
			rejected.length > 0
				? `Формат не поддерживается: ${rejected.join(', ')}. Допустимы ${ACCEPTED_EXTENSIONS.join(', ')}.`
				: null;
	}

	function onDragEnter(event: DragEvent) {
		event.preventDefault();
		dragDepth += 1;
	}

	function onDrop(event: DragEvent) {
		event.preventDefault();
		dragDepth = 0;
		addFiles(event.dataTransfer?.files);
	}

	function onPick(event: Event & { currentTarget: HTMLInputElement }) {
		addFiles(event.currentTarget.files);
		// Reset so that picking the same file again fires `change`.
		event.currentTarget.value = '';
	}
</script>

{#snippet picker()}
	<div
		class={[
			'grid gap-1',
			!single && [
				'rounded-lg border-[1.5px] border-dashed px-4 py-5 text-center transition-colors',
				dragDepth > 0 ? 'border-accent bg-accent-soft' : 'border-line'
			]
		]}
	>
		<p class="text-sm">
			{single ? 'Перетащите файл сюда или' : 'Перетащите файлы сюда или'}
			<label
				class="cursor-pointer rounded font-medium text-accent underline underline-offset-2 has-focus-visible:outline-2 has-focus-visible:outline-accent"
			>
				выберите на компьютере
				<input
					type="file"
					multiple={!single}
					accept={ACCEPT_ATTRIBUTE}
					class="sr-only"
					onchange={onPick}
				/>
			</label>
		</p>
		<p class="text-xs text-muted">
			{single
				? 'Word, PDF или Excel. Штатное расписание — внутри документа.'
				: `Word, PDF или Excel: ${ACCEPTED_EXTENSIONS.join(', ')}`}
		</p>
	</div>
{/snippet}

<div
	role="region"
	aria-labelledby={headingId}
	class={[
		'grid grid-cols-1 content-start gap-2',
		single && [
			'rounded-lg border-[1.5px] border-dashed border-accent p-4 transition-colors',
			dragDepth > 0 && accepting ? 'bg-accent-soft' : 'bg-surface'
		]
	]}
	ondragenter={onDragEnter}
	ondragover={(event) => event.preventDefault()}
	ondragleave={() => (dragDepth = Math.max(0, dragDepth - 1))}
	ondrop={onDrop}
>
	{#if single}
		<span class="text-xs font-medium tracking-[0.07em] text-muted uppercase">Обязательно</span>
		<h2 id={headingId} class="text-lg font-semibold">{info.title}</h2>
	{:else}
		<h3 id={headingId} class="font-semibold">{info.title}</h3>
	{/if}
	<p class="text-sm text-muted">{info.hint}</p>

	{#if accepting}
		{@render picker()}
	{/if}

	<!-- File names can be one long word; wrap them anywhere rather than widen a phone screen. -->
	{#if message}
		<p class="text-sm wrap-anywhere text-bad" role="alert">{message}</p>
	{/if}
	{#if refused && !accepting}
		<p class="text-sm text-bad" role="alert">
			Файл уже загружен. Удалите его, чтобы выбрать другой.
		</p>
	{/if}

	{#if items.length > 0}
		<ul class="flex flex-col gap-2">
			{#each items as item (item.key)}
				<FileRow {item} {session} />
			{/each}
		</ul>
	{/if}
</div>
