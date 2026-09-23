<script lang="ts">
	import type { NodeOut } from '$lib/api/document';
	import { alignDocuments, type DiffRow, type RowStatus } from '$lib/diff/align';
	import { nodeAnchorId, parseNodeHash } from '$lib/diff/anchor';
	import type { CompareSide } from '$lib/diff/view.svelte';
	import { diffWords } from '$lib/diff/words';

	interface Props {
		before: CompareSide;
		after: CompareSide;
		/** Location hash; `#node-<id>` scrolls to that node and highlights it. */
		hash?: string;
	}

	let { before, after, hash = '' }: Props = $props();

	let onlyChanges = $state(true);

	const blocks = $derived(alignDocuments(before.nodes, after.nodes));
	const targetId = $derived(parseNodeHash(hash));
	const allRows = $derived(
		blocks.flatMap((block) => (block.head === null ? block.rows : [block.head, ...block.rows]))
	);
	const counts = $derived(
		allRows.reduce((total, row) => ({ ...total, [row.status]: total[row.status] + 1 }), {
			unchanged: 0,
			changed: 0,
			removed: 0,
			added: 0
		} satisfies Record<RowStatus, number>)
	);
	const targetMissing = $derived(targetId !== null && !allRows.some(isTarget));

	/** Blocks as shown: with «Только изменения», unchanged rows go, except the linked one. */
	const shown = $derived(
		blocks
			.map((block) => ({
				key: rowKey(block.head ?? block.rows[0]),
				head: block.head,
				rows: block.rows.filter(isShown)
			}))
			.filter(
				(block) =>
					!onlyChanges || block.rows.length > 0 || (block.head !== null && isShown(block.head))
			)
	);

	/** The longest indent; deeper nodes line up with it so the text keeps its width. */
	const MAX_INDENT = 5;

	const STATUS_BORDERS: Record<RowStatus, string> = {
		unchanged: 'border-l-transparent',
		changed: 'border-l-warn',
		removed: 'border-l-bad',
		added: 'border-l-ok'
	};

	function rowKey(row: DiffRow): string {
		return `${row.before?.id ?? '-'}/${row.after?.id ?? '-'}`;
	}

	function isTarget(row: DiffRow): boolean {
		return targetId !== null && (row.before?.id === targetId || row.after?.id === targetId);
	}

	function isShown(row: DiffRow): boolean {
		return !onlyChanges || row.status !== 'unchanged' || isTarget(row);
	}

	function documentName(side: CompareSide): string {
		return side.document.title ?? side.document.file_name;
	}

	/** Brings the linked node into view and focus once it is on the page. */
	function revealTarget(container: HTMLElement) {
		if (targetId === null) {
			return;
		}
		const anchor = container.querySelector(`#${CSS.escape(nodeAnchorId(targetId))}`);
		const row = anchor?.closest<HTMLElement>('[data-row]');
		if (row) {
			const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
			row.scrollIntoView({ block: 'center', behavior: calm ? 'auto' : 'smooth' });
			row.focus({ preventScroll: true });
		}
	}
</script>

{#snippet ref(label: string, node: NodeOut | null)}
	<span class="block" id={node === null ? undefined : nodeAnchorId(node.id)}>
		{label}: {node === null ? '—' : node.anchor}
	</span>
{/snippet}

{#snippet text(row: DiffRow)}
	{#if row.status === 'changed' && row.before !== null && row.after !== null}
		{#each diffWords(row.before.text, row.after.text) as part, index (index)}
			{#if part.op === 'delete'}<del>{part.text}</del>{:else if part.op === 'insert'}<ins
					>{part.text}</ins
				>{:else}{part.text}{/if}
		{/each}
	{:else if row.status === 'removed'}
		<del>{row.before?.text}</del>
	{:else if row.status === 'added'}
		<ins>{row.after?.text}</ins>
	{:else}
		{row.after?.text}
	{/if}
{/snippet}

{#snippet line(row: DiffRow, heading: boolean)}
	<div
		data-row
		data-status={row.status}
		tabindex="-1"
		aria-current={isTarget(row) ? 'location' : undefined}
		class={[
			'grid grid-cols-[10.5rem_1fr] gap-3 border-l-[3px] px-3.5 py-2 outline-none',
			'transition-colors duration-500 aria-[current=location]:bg-hl',
			'aria-[current=location]:ring-2 aria-[current=location]:ring-accent aria-[current=location]:ring-inset',
			STATUS_BORDERS[row.status],
			heading ? 'bg-page' : 'border-b [border-bottom-style:dashed] border-b-line last:border-b-0'
		]}
	>
		<div class="font-mono text-[0.78rem]/[1.5] break-words text-muted">
			{@render ref('до', row.before)}
			{@render ref('после', row.after)}
		</div>
		<svelte:element
			this={heading ? 'h3' : 'p'}
			class={['break-words whitespace-pre-line', heading && 'font-semibold']}
			style:padding-left="{Math.min(Math.max(row.depth - 1, 0), MAX_INDENT) * 1.25}rem"
		>
			{@render text(row)}
		</svelte:element>
	</div>
{/snippet}

<div class="grid gap-4">
	<header class="grid grid-cols-2 gap-3">
		{#each [{ label: 'До', side: before }, { label: 'После', side: after }] as { label, side } (label)}
			<div class="grid content-start gap-0.5 rounded-lg border border-line bg-surface px-4 py-3">
				<p class="text-xs font-medium tracking-[0.07em] text-muted uppercase">{label}</p>
				<h2 class="font-semibold break-words">{documentName(side)}</h2>
				{#if side.document.title !== null}
					<p class="text-sm break-words text-muted">{side.document.file_name}</p>
				{/if}
			</div>
		{/each}
	</header>

	<div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
		<span>Изменено: <strong>{counts.changed}</strong></span>
		<span>
			<span class="text-bad line-through decoration-[1.5px]">Удалено</span>:
			<strong>{counts.removed}</strong>
		</span>
		<span>
			<span class="rounded-xs bg-ok-soft text-ok underline decoration-[1.5px] underline-offset-2">
				Добавлено
			</span>:
			<strong>{counts.added}</strong>
		</span>
		<span class="text-muted">Без изменений: {counts.unchanged}</span>
		<label class="ml-auto flex cursor-pointer items-center gap-2 font-medium">
			<input type="checkbox" class="size-4 accent-accent" bind:checked={onlyChanges} />
			Только изменения
		</label>
	</div>

	{#if targetMissing}
		<p class="rounded-md border border-warn bg-warn-soft px-3 py-2 text-sm text-warn" role="status">
			Пункт из ссылки не найден в сравниваемых документах.
		</p>
	{/if}

	{#if allRows.length === 0}
		<p class="rounded-lg border border-line bg-surface p-4 text-muted">
			В документах не найдено ни одного пункта.
		</p>
	{:else if shown.length === 0}
		<p class="rounded-lg border border-line bg-surface p-4 text-muted">
			Изменений нет: тексты пунктов совпадают.
		</p>
	{:else}
		<div class="overflow-hidden rounded-lg border border-line bg-surface" {@attach revealTarget}>
			{#each shown as block (block.key)}
				<section class="border-b border-line last:border-b-0">
					{#if block.head === null}
						<h3 class="border-b border-line bg-page px-3.5 py-2 text-sm text-muted">
							Текст вне разделов
						</h3>
					{:else}
						<div class="border-b border-line">{@render line(block.head, true)}</div>
					{/if}
					{#each block.rows as row (rowKey(row))}
						{@render line(row, false)}
					{/each}
				</section>
			{/each}
		</div>
	{/if}
</div>

<style>
	del {
		color: var(--bad);
		text-decoration: line-through;
		text-decoration-thickness: 1.5px;
	}

	ins {
		color: var(--ok);
		text-decoration: underline;
		text-decoration-thickness: 1.5px;
		text-underline-offset: 2px;
		background: var(--ok-soft);
		border-radius: 2px;
	}

	/* Screen readers do not announce <del> and <ins> by themselves. */
	del::before,
	ins::before {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}

	del::before {
		content: 'удалено: ';
	}

	ins::before {
		content: 'добавлено: ';
	}
</style>
