<script lang="ts">
	import { SvelteMap } from 'svelte/reactivity';
	import type { Activity, Entity } from '$lib/api/registries';
	import { ACTIVITY_LABELS, PARTICIPATION_LABELS, REVIEW_LABELS } from '$lib/registry/labels';
	import type { SourceTarget } from '$lib/source/panel.svelte';
	import RegistrySources from './RegistrySources.svelte';

	let {
		activities,
		entities,
		entityFilter = $bindable('all'),
		onopen
	}: {
		activities: Activity[];
		entities: Entity[];
		entityFilter?: string;
		onopen: (targets: SourceTarget[], index?: number) => void;
	} = $props();
	let type = $state('all');
	let search = $state('');
	const owners = $derived.by(() => {
		const names = new SvelteMap(entities.map((item) => [item.id, item.name]));
		for (const record of activities) {
			if (record.entity_id !== null && !names.has(record.entity_id))
				names.set(record.entity_id, record.entity_name ?? 'Объект');
		}
		return [...names];
	});
	const shown = $derived(
		activities.filter(
			(item) =>
				(entityFilter === 'all' ||
					(entityFilter === 'unknown'
						? item.entity_id === null
						: String(item.entity_id) === entityFilter)) &&
				(type === 'all' || item.record_type === type) &&
				item.formulation.toLocaleLowerCase().includes(search.toLocaleLowerCase().trim())
		)
	);
</script>

<div class="grid gap-3">
	<div class="grid gap-2 sm:grid-cols-3">
		<label class="grid gap-1 text-sm"
			>Исполнитель
			<select bind:value={entityFilter} class="min-w-0 rounded border border-line bg-page p-2">
				<option value="all">Все исполнители</option><option value="unknown"
					>Исполнитель не установлен</option
				>
				{#each owners as [id, name] (id)}<option value={String(id)}>{name} · #{id}</option>{/each}
			</select>
		</label>
		<label class="grid gap-1 text-sm"
			>Тип записи
			<select bind:value={type} class="rounded border border-line bg-page p-2">
				<option value="all">Все типы</option>
				{#each Object.entries(ACTIVITY_LABELS) as [key, label] (key)}<option value={key}
						>{label}</option
					>{/each}
			</select>
		</label>
		<label class="grid gap-1 text-sm"
			>Поиск деятельности
			<input
				type="search"
				bind:value={search}
				class="min-w-0 rounded border border-line bg-page p-2"
			/>
		</label>
	</div>
	<p class="text-sm text-muted">
		Показано записей: {shown.length} из {activities.length}. Каждая запись относится к своему
		исполнителю; одинаковые формулировки не объединены.
	</p>
	{#if shown.length === 0}<p>
			Нет записей для отображения по выбранным фильтрам. Проверьте статус обработки выше.
		</p>{/if}
	{#each shown as record (record.id)}
		<article
			class="grid gap-2 rounded border border-line p-3 wrap-anywhere"
			aria-label={`Запись #${record.id}`}
		>
			<h3 class="font-semibold">{ACTIVITY_LABELS[record.record_type]} · #{record.id}</h3>
			<p class="text-sm">
				Исполнитель: {record.entity_id === null
					? 'не установлен'
					: `${record.entity_name ?? 'Объект'} · #${record.entity_id}`}
			</p>
			<p class="text-sm">Обозначение в документе: {record.designation || 'не указано'}</p>
			<p class="whitespace-pre-wrap">{record.formulation}</p>
			<dl class="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
				<dt class="text-muted">Условие</dt>
				<dd>{record.condition ?? 'не указано'}</dd>
				<dt class="text-muted">Срок</dt>
				<dd>{record.deadline ?? 'не указан'}</dd>
				<dt class="text-muted">Периодичность</dt>
				<dd>{record.periodicity ?? 'не указана'}</dd>
				<dt class="text-muted">Участие</dt>
				<dd>{PARTICIPATION_LABELS[record.participation]}</dd>
				<dt class="text-muted">Состав участников</dt>
				<dd>{record.participant_designation || 'не указан'}</dd>
				<dt class="text-muted">Другие участники</dt>
				<dd>
					{record.other_participants
						.map((item) => `${item.entity_name ?? 'Объект'} · #${item.entity_id}`)
						.join('; ') || 'не указаны'}
				</dd>
				<dt class="text-muted">Конкретность</dt>
				<dd>
					{record.specificity === 'specific'
						? 'Конкретная запись'
						: record.specificity === 'generalized'
							? 'Обобщённая запись'
							: 'Требуется уточнение'}
				</dd>
				<dt class="text-muted">Проверка</dt>
				<dd>{REVIEW_LABELS[record.review_status]}</dd>
			</dl>
			{#if record.note}<p class="rounded bg-warn-soft p-2 text-sm text-warn">{record.note}</p>{/if}
			<RegistrySources sources={record.sources} {onopen} />
		</article>
	{/each}
</div>
