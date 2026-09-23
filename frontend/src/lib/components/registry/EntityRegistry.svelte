<script lang="ts">
	import type { Entity, EntityRelation } from '$lib/api/registries';
	import { entityLabel, entityPath } from '$lib/registry/entities';
	import { CATEGORY_LABELS, RELATION_LABELS, REVIEW_LABELS } from '$lib/registry/labels';
	import type { SourceTarget } from '$lib/source/panel.svelte';
	import RegistrySources from './RegistrySources.svelte';

	let {
		entities,
		relations,
		onopen,
		onactivities
	}: {
		entities: Entity[];
		relations: EntityRelation[];
		onopen: (targets: SourceTarget[], index?: number) => void;
		onactivities: (id: number) => void;
	} = $props();
	let search = $state('');
	const shown = $derived(
		entities.filter((item) =>
			[
				item.name,
				...item.aliases,
				item.id.toString(),
				item.entity_type,
				...item.roles.map((role) => role.role)
			]
				.join(' ')
				.toLocaleLowerCase()
				.includes(search.toLocaleLowerCase().trim())
		)
	);
</script>

<div class="grid gap-3">
	<label class="grid gap-1 text-sm"
		>Поиск объектов
		<input
			type="search"
			bind:value={search}
			class="rounded border border-line bg-page p-2"
			placeholder="Название, ID, тип или роль"
		/>
	</label>
	<p class="text-sm text-muted">
		Показано объектов: {shown.length} из {entities.length}. Статус «Технически проверено» не
		означает подтверждение сотрудником.
	</p>
	{#if shown.length === 0}<p>
			Нет записей для отображения{search.trim() ? ' по выбранному фильтру' : ''}.
		</p>{/if}
	{#each shown as entity (entity.id)}
		<article
			class="grid gap-2 rounded border border-line p-3 wrap-anywhere"
			aria-label={`Объект #${entity.id}`}
		>
			<h3 class="font-semibold">{entity.name} <span class="text-muted">· #{entity.id}</span></h3>
			<p class="text-sm text-muted">
				{entity.entity_type} · {CATEGORY_LABELS[entity.category] ?? entity.category} · {REVIEW_LABELS[
					entity.review_status
				]}
			</p>
			<p class="text-sm">Принадлежность: {entityPath(entity, entities)}</p>
			{#if entity.parent_status === 'root'}<p class="text-sm">Корневой объект по документу</p>{/if}
			{#if entity.parent_status === 'ambiguous'}
				<p class="text-sm text-warn">
					Кандидаты в родители: {entity.parent_candidates
						.map((id) => entityLabel(id, entities))
						.join('; ') || 'не указаны'}
				</p>
			{/if}
			{#if entity.aliases.length}<p class="text-sm">
					Другие названия: {entity.aliases.join('; ')}
				</p>{/if}
			<p class="text-sm">
				Тип позиции: {entity.position_type ?? 'не указан'} · Уровень: {entity.level ?? 'не указан'}
			</p>
			{#each entity.roles as role, index (index)}<p class="text-sm">
					Роль: {role.role}{role.scope ? ` — ${role.scope}` : ''}
				</p>{/each}
			<button
				type="button"
				class="justify-self-start text-sm text-accent hover:underline"
				onclick={() => onactivities(entity.id)}>Деятельность объекта #{entity.id}</button
			>
			<RegistrySources sources={entity.sources} {onopen} />
		</article>
	{/each}
	<details>
		<summary class="cursor-pointer font-medium">Дополнительные связи ({relations.length})</summary>
		<p class="my-2 text-sm text-muted">Эти связи не заменяют организационного родителя.</p>
		{#each relations as relation (relation.id)}
			<article class="mb-2 rounded border border-line p-3 text-sm wrap-anywhere">
				<p>
					{entityLabel(relation.from_entity_id, entities)} → {RELATION_LABELS[
						relation.relation_type
					] ?? relation.relation_type} → {entityLabel(relation.to_entity_id, entities)}
				</p>
				<p>Условия: {relation.conditions ?? 'не указаны'}</p>
				<RegistrySources sources={relation.sources} {onopen} />
			</article>
		{/each}
	</details>
</div>
