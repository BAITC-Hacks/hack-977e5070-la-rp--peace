<script lang="ts">
	import { resolve } from '$app/paths';
	import UploadZone from '$lib/components/UploadZone.svelte';
	import { DOC_SETS } from '$lib/documents';
	import { uploadSession as session } from '$lib/upload/current';
	import { launchBlocker } from '$lib/upload/launch';

	const hintId = $props.id();
	const required = DOC_SETS.filter((info) => !info.optional);
	const external = DOC_SETS.filter((info) => info.optional);
	const externalCount = $derived(
		external.reduce((count, info) => count + session.itemsIn(info.set).length, 0)
	);
	const blocker = $derived(launchBlocker(session.items));
</script>

<svelte:head><title>Анализ реорганизации</title></svelte:head>

<div class="grid grid-cols-1 gap-5">
	<div class="grid gap-1.5">
		<h1 class="text-2xl font-semibold text-balance">Анализ реорганизации</h1>
		<p class="max-w-[72ch] text-muted">
			Загрузите положение и штатное расписание до и после реорганизации. Агент покажет, что
			изменилось, и найдёт потерю функций, дублирование и конфликт интересов — со ссылкой на пункт
			документа.
		</p>
	</div>

	<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
		{#each required as info (info.set)}
			<UploadZone {session} {info} />
		{/each}
	</div>

	<details class="group rounded-lg border border-line bg-surface p-4">
		<summary
			class="flex cursor-pointer list-none items-center gap-3 [&::-webkit-details-marker]:hidden"
		>
			<svg
				viewBox="0 0 20 20"
				fill="currentColor"
				class="size-5 shrink-0 text-muted transition-transform group-open:rotate-90"
				aria-hidden="true"
			>
				<path
					d="M8.22 5.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.75.75 0 0 1-1.06-1.06L11.94 10 8.22 6.28a.75.75 0 0 1 0-1.06Z"
				/>
			</svg>
			<span class="grid">
				<span class="text-xs font-medium tracking-[0.07em] text-muted uppercase">
					Необязательно
				</span>
				<span class="text-lg font-semibold">Внешние документы</span>
			</span>
			{#if externalCount > 0}
				<span class="ml-auto text-sm text-muted">файлов: {externalCount}</span>
			{/if}
		</summary>
		<div class="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-2">
			{#each external as info (info.set)}
				<UploadZone {session} {info} />
			{/each}
		</div>
	</details>

	<div class="grid justify-items-start gap-2">
		<!-- The status screen follows the same files: uploads and parsing still in progress included. -->
		{#if blocker}
			<button
				type="button"
				class="rounded-md bg-accent px-[18px] py-2.5 font-semibold text-accent-ink disabled:cursor-not-allowed disabled:opacity-50"
				disabled
				aria-describedby={hintId}
			>
				Начать анализ
			</button>
			<!-- The hint may name a file: a long name wraps instead of widening a phone screen. -->
			<p id={hintId} class="max-w-full text-sm wrap-anywhere text-muted">{blocker}</p>
		{:else}
			<a
				href={resolve('/status')}
				class="rounded-md bg-accent px-[18px] py-2.5 font-semibold text-accent-ink"
			>
				Начать анализ
			</a>
		{/if}
	</div>
</div>
