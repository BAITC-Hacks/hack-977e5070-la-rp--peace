<script lang="ts">
	import type { RegistrySource } from '$lib/api/registries';
	import { SUPPORT_LABELS } from '$lib/registry/labels';
	import type { SourceTarget } from '$lib/source/panel.svelte';

	let {
		sources,
		onopen
	}: {
		sources: RegistrySource[];
		onopen: (targets: SourceTarget[], index?: number) => void;
	} = $props();

	function open(index: number) {
		onopen(
			sources.map((source) => ({ nodeId: source.node_id, quote: source.quote })),
			index
		);
	}
</script>

{#if sources.length === 0}
	<p class="text-sm text-warn">Нет подтверждения в документах.</p>
{:else}
	<details class="mt-2">
		<summary class="cursor-pointer text-sm font-medium text-accent"
			>Источники ({sources.length})</summary
		>
		<ul class="mt-2 grid gap-2">
			{#each sources as source, index (index)}
				<li>
					<button
						type="button"
						class="grid w-full gap-1 rounded border border-line bg-page p-2 text-left text-sm wrap-anywhere hover:border-accent"
						onclick={() => open(index)}
					>
						<span class="font-medium text-accent">{source.path} — открыть источник</span>
						<span>«{source.quote}»</span>
						<span class="text-xs text-muted"
							>Подтверждает: {source.supports.map((key) => SUPPORT_LABELS[key] ?? key).join(', ') ||
								'не указано'}</span
						>
					</button>
				</li>
			{/each}
		</ul>
	</details>
{/if}
