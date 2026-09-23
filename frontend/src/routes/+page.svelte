<script lang="ts">
	import { documentsApi } from '$lib/api/client';
	import UploadZone from '$lib/components/UploadZone.svelte';
	import { DOC_SETS } from '$lib/documents';
	import { UploadSession } from '$lib/upload/session.svelte';

	const session = new UploadSession(documentsApi);
	const required = DOC_SETS.filter((info) => !info.optional);
	const optional = DOC_SETS.filter((info) => info.optional);
</script>

<svelte:head><title>Новый анализ — Анализ оргструктуры и функционала</title></svelte:head>

<h1 class="text-2xl font-semibold">Новый анализ</h1>
<p class="mt-2 max-w-3xl text-slate-600">
	Загрузите комплекты документов до и после реорганизации. Тип каждого документа определяется
	автоматически — если он определён неверно, исправьте его в списке файлов.
</p>

<div class="mt-6 grid gap-6 lg:grid-cols-2">
	{#each required as info (info.set)}
		<UploadZone {session} {info} />
	{/each}
</div>

<div class="mt-6 grid gap-6 lg:grid-cols-2">
	{#each optional as info (info.set)}
		<UploadZone {session} {info} />
	{/each}
</div>
