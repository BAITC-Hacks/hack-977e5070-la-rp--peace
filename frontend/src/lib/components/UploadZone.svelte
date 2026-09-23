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

	// dragenter/dragleave also fire for child elements, so count them instead of toggling a flag.
	let dragDepth = $state(0);
	let rejected = $state<string[]>([]);

	function addFiles(files: FileList | null | undefined) {
		if (files && files.length > 0) {
			rejected = session.add(info.set, files);
		}
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

{#snippet body()}
	<p class="mt-1 text-sm text-slate-600">{info.hint}</p>
	<div
		role="region"
		aria-label={`Зона загрузки: ${info.title}`}
		class={[
			'mt-3 rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors',
			dragDepth > 0 ? 'border-blue-500 bg-blue-50' : 'border-slate-300 bg-slate-50'
		]}
		ondragenter={onDragEnter}
		ondragover={(event) => event.preventDefault()}
		ondragleave={() => (dragDepth = Math.max(0, dragDepth - 1))}
		ondrop={onDrop}
	>
		<p class="text-sm text-slate-700">
			Перетащите файлы сюда или
			<label
				class="cursor-pointer rounded font-medium text-blue-700 underline underline-offset-2 hover:text-blue-900 has-focus-visible:outline-2 has-focus-visible:outline-blue-600"
			>
				выберите на компьютере
				<input type="file" multiple accept={ACCEPT_ATTRIBUTE} class="sr-only" onchange={onPick} />
			</label>
		</p>
		<p class="mt-1 text-xs text-slate-500">Word, PDF или Excel: {ACCEPTED_EXTENSIONS.join(', ')}</p>
	</div>

	{#if rejected.length > 0}
		<p class="mt-2 text-sm text-red-700" role="alert">
			Формат не поддерживается: {rejected.join(', ')}. Допустимы {ACCEPTED_EXTENSIONS.join(', ')}.
		</p>
	{/if}

	{#if items.length > 0}
		<ul class="mt-3 flex flex-col gap-2">
			{#each items as item (item.key)}
				<FileRow {item} {session} />
			{/each}
		</ul>
	{/if}
{/snippet}

{#if info.optional}
	<details class="group rounded-xl border border-slate-200 bg-white p-5">
		<summary class="flex cursor-pointer items-center gap-2">
			<svg
				viewBox="0 0 20 20"
				fill="currentColor"
				class="size-5 shrink-0 text-slate-400 transition-transform group-open:rotate-90"
				aria-hidden="true"
			>
				<path
					d="M8.22 5.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.75.75 0 0 1-1.06-1.06L11.94 10 8.22 6.28a.75.75 0 0 1 0-1.06Z"
				/>
			</svg>
			<h2 id={headingId} class="text-lg font-semibold">{info.title}</h2>
			<span class="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
				необязательно
			</span>
			{#if items.length > 0}
				<span class="text-xs text-slate-500">файлов: {items.length}</span>
			{/if}
		</summary>
		{@render body()}
	</details>
{:else}
	<section class="rounded-xl border border-slate-200 bg-white p-5" aria-labelledby={headingId}>
		<h2 id={headingId} class="text-lg font-semibold">{info.title}</h2>
		{@render body()}
	</section>
{/if}
