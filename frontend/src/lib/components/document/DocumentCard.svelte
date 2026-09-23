<script lang="ts">
	import type { DocumentCardValues } from '$lib/api/document';
	import { cardFields, extraFields, extraKey, isCardEmpty } from '$lib/document/card';

	interface Props {
		card: DocumentCardValues;
		/** `metadata_evidence` from `GET /api/documents/{id}/profile`. */
		evidence: Record<string, unknown>;
	}

	let { card, evidence }: Props = $props();

	const fields = $derived(cardFields(card, evidence));
	const extra = $derived(extraFields(evidence));
</script>

{#snippet quotes(texts: string[])}
	{#if texts.length > 0}
		<ul class="mt-1 grid gap-1" aria-label="Цитаты из документа">
			{#each texts as text (text)}
				<li class="border-l-2 border-line pl-2 text-sm text-muted">«{text}»</li>
			{/each}
		</ul>
	{/if}
{/snippet}

{#if isCardEmpty(fields) && extra.length === 0}
	<p class="text-sm text-muted">Реквизиты не извлечены.</p>
{:else}
	<dl class="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-[13rem_minmax(0,1fr)] sm:gap-y-3">
		{#each fields as field (field.name)}
			<dt class="pt-0.5 text-xs font-medium tracking-[0.07em] text-muted uppercase">
				{field.label}
			</dt>
			<dd class="mb-2 sm:mb-0" data-field={field.name}>
				{#if field.state === 'confirmed'}
					<p>{field.value}</p>
					{@render quotes(field.quotes)}
				{:else if field.state === 'manual'}
					<p>
						{field.value}
						<span class="text-xs text-muted">· указано вручную, цитаты нет</span>
					</p>
				{:else if field.state === 'ambiguous'}
					<div class="grid gap-0.5 rounded-md bg-warn-soft px-2.5 py-1.5 text-warn">
						<p class="text-sm font-medium">
							Не подтверждено{field.value === null ? '' : `: ${field.value}`}
						</p>
						{#if field.reason}
							<p class="text-sm">{field.reason}</p>
						{/if}
						{@render quotes(field.quotes)}
					</div>
				{:else if field.state === 'not_found'}
					<p class="text-muted">
						не найдено{field.reason === null ? '' : ` — ${field.reason}`}
					</p>
				{:else}
					<p class="text-muted">нет данных</p>
				{/if}
			</dd>
		{/each}

		{#each extra as item (extraKey(item))}
			<dt class="pt-0.5 text-xs font-medium tracking-[0.07em] text-muted uppercase">
				{item.name}
			</dt>
			<dd class="mb-2 sm:mb-0">
				<p>{item.value}</p>
				{@render quotes(item.quotes)}
			</dd>
		{/each}
	</dl>
{/if}
