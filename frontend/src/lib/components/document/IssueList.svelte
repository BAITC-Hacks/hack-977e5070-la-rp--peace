<script lang="ts">
	import type { IssueOut } from '$lib/api/document';
	import { sortIssues } from '$lib/document/issues';
	import { issueTypeLabel } from '$lib/document/labels';

	interface Props {
		issues: IssueOut[];
		/** Short place of each node («п. 3.4»), shown next to the issues that point at one. */
		anchors?: ReadonlyMap<number, string>;
		/** Shows the node in the document tree; without it the issues have no «К пункту» buttons. */
		onreveal?: (nodeId: number) => void;
	}

	let { issues, anchors, onreveal }: Props = $props();

	const sorted = $derived(sortIssues(issues));
</script>

{#if sorted.length === 0}
	<p class="text-sm text-muted">Проблем разбора не найдено.</p>
{:else}
	<ul class="grid gap-2">
		{#each sorted as issue (issue.id)}
			{@const nodeId = issue.node_id}
			{@const anchor = nodeId === null ? undefined : anchors?.get(nodeId)}
			{@const resolved = issue.resolved_at !== null}
			<li
				class={[
					'rounded-md border p-3',
					resolved && 'border-line bg-surface opacity-70',
					!resolved && issue.is_blocking && 'border-bad bg-bad-soft',
					!resolved && !issue.is_blocking && 'border-line bg-surface'
				]}
			>
				<div class="flex flex-wrap items-center gap-x-2 gap-y-1">
					<span
						class={[
							'rounded px-1.5 py-0.5 text-xs font-semibold',
							resolved && 'bg-neutral-soft text-neutral',
							!resolved && issue.is_blocking && 'bg-bad text-surface',
							!resolved && !issue.is_blocking && 'bg-warn-soft text-warn'
						]}
					>
						{resolved ? 'Решена' : issue.is_blocking ? 'Блокирующая' : 'Предупреждение'}
					</span>
					<span class="text-sm font-medium">{issueTypeLabel(issue.issue_type)}</span>
					{#if anchor}
						<span class="font-mono text-xs text-muted">{anchor}</span>
					{/if}
					{#if nodeId !== null && onreveal}
						<button
							type="button"
							class="ml-auto text-sm text-accent hover:underline"
							aria-label={anchor ? `К пункту ${anchor}` : undefined}
							onclick={() => onreveal(nodeId)}
						>
							К пункту
						</button>
					{/if}
				</div>
				<p class="mt-1 text-sm break-words">{issue.message}</p>
			</li>
		{/each}
	</ul>
{/if}
