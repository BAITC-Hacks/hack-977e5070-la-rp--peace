<script lang="ts">
	import { onMount } from 'svelte';
	import { registriesApi, type RegistriesApi } from '$lib/api/registries';
	import { RegistryView } from '$lib/registry/view.svelte';
	import type { SourceTarget } from '$lib/source/panel.svelte';
	import ActivityRegistry from './ActivityRegistry.svelte';
	import EntityRegistry from './EntityRegistry.svelte';
	import ExtractionReport from './ExtractionReport.svelte';

	// The document page keys this component by documentId; pending responses are stopped on exit.
	let {
		documentId,
		onopen,
		api = registriesApi
	}: {
		documentId: number;
		onopen: (targets: SourceTarget[], index?: number) => void;
		api?: RegistriesApi;
	} = $props();
	const entities = new RegistryView(() => api.entities(documentId));
	const activities = new RegistryView(() => api.activities(documentId));
	let active = $state<'entities' | 'activities'>('entities');
	let entityFilter = $state('all');
	const current = $derived(active === 'entities' ? entities : activities);
	const headingId = $props.id();

	onMount(() => {
		entities.start();
		activities.start();
		return () => {
			entities.stop();
			activities.stop();
		};
	});

	function showActivities(id: number) {
		entityFilter = String(id);
		active = 'activities';
	}
</script>

<section
	class="grid min-w-0 gap-4 rounded-lg border border-line bg-surface p-4"
	aria-labelledby={headingId}
>
	<h2 id={headingId} class="text-lg font-semibold">
		Объекты и деятельность документа #{documentId}
	</h2>
	<p class="text-sm text-muted">
		Независимый реестр этого документа. Связи с другими редакциями здесь не устанавливаются.
	</p>
	<div class="flex flex-wrap gap-2" role="group" aria-label="Реестры документа">
		<button
			type="button"
			aria-pressed={active === 'entities'}
			class="rounded border border-line px-3 py-1.5 text-sm aria-pressed:bg-accent aria-pressed:text-accent-ink"
			onclick={() => (active = 'entities')}>Объекты</button
		>
		<button
			type="button"
			aria-pressed={active === 'activities'}
			class="rounded border border-line px-3 py-1.5 text-sm aria-pressed:bg-accent aria-pressed:text-accent-ink"
			onclick={() => (active = 'activities')}>Деятельность</button
		>
		<button
			type="button"
			class="ml-auto rounded border border-line px-3 py-1.5 text-sm disabled:opacity-50"
			disabled={current.loading}
			onclick={() => current.refresh()}>Обновить данные</button
		>
	</div>
	{#if current.error}
		<p role="alert" class="rounded bg-bad-soft p-3 text-sm text-bad">
			Не удалось обновить данные: {current.error}{current.data
				? ' Показан ранее загруженный результат.'
				: ''}
		</p>
	{/if}
	{#if current.loading && !current.data}<p role="status">Загрузка реестра…</p>{/if}
	{#if current.data}<ExtractionReport
			report={current.data.report}
			status={current.data.status}
			{onopen}
		/>{/if}
	{#if active === 'entities' && entities.data}
		<EntityRegistry
			entities={entities.data.items}
			relations={entities.data.relations}
			{onopen}
			onactivities={showActivities}
		/>
	{:else if active === 'activities' && activities.data}
		<ActivityRegistry
			activities={activities.data.items}
			entities={entities.data?.items ?? []}
			bind:entityFilter
			{onopen}
		/>
	{/if}
</section>
