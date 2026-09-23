<script lang="ts">
	import type { ExtractionReport, ExtractionStatus } from '$lib/api/registries';
	import { BLOCK_LABELS, STAGE_LABELS } from '$lib/registry/labels';
	import type { SourceTarget } from '$lib/source/panel.svelte';

	let {
		report,
		status,
		onopen
	}: {
		report: ExtractionReport;
		status: ExtractionStatus;
		onopen: (targets: SourceTarget[]) => void;
	} = $props();
	const successful = $derived(
		report.blocks.filter((block) => block.status === 'found' || block.status === 'none').length
	);
	const openIssues = $derived(report.issues.filter((issue) => issue.resolved_at === null));
</script>

<div class="grid gap-2 text-sm">
	<p role="status" class={status === 'done' ? 'text-ok' : 'text-warn'}>{STAGE_LABELS[status]}</p>
	{#if status !== 'done'}
		<p class="rounded bg-warn-soft p-2 text-warn">
			Результат не окончательный. При повторной обработке здесь могут оставаться записи предыдущего
			запуска. Отсутствие записей не доказывает отсутствие сведений в документе.
		</p>
	{/if}
	<p class="text-muted">
		Сохранённых блоков без ошибок и уточнений: {successful} из {report.blocks.length}. Открытых
		замечаний: {openIssues.length}.
	</p>
	<details>
		<summary class="cursor-pointer text-accent">Отчёт обработки и замечания</summary>
		<ul class="mt-2 grid gap-2">
			{#each report.issues as issue (issue.id)}
				<li class="rounded border border-line p-2 wrap-anywhere">
					<p class="font-medium">
						{issue.resolved_at !== null
							? 'Решено'
							: issue.is_blocking
								? 'Блокирующее замечание'
								: 'Замечание'} · #{issue.id}
					</p>
					<p>{issue.message}</p>
					{#if issue.entity_id != null}<p>Объект #{issue.entity_id}</p>{/if}
					{#if issue.record_id != null}<p>Запись #{issue.record_id}</p>{/if}
					{#if issue.relation_id != null}<p>Связь #{issue.relation_id}</p>{/if}
				</li>
			{/each}
			{#each report.blocks as block (block.node_id)}
				<li class="rounded border border-line p-2 wrap-anywhere">
					<button
						type="button"
						class="text-left text-accent hover:underline"
						onclick={() => onopen([{ nodeId: block.node_id }])}>{block.path}</button
					>
					<p>{BLOCK_LABELS[block.status]} · попыток: {block.attempts}</p>
					{#if block.message}<p>{block.message}</p>{/if}
				</li>
			{/each}
		</ul>
	</details>
</div>
