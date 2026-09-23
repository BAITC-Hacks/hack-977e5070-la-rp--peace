<script lang="ts">
	import { tick } from 'svelte';

	import { NODE_TYPE_LABELS } from '$lib/document/labels';
	import { excerpt, type TreeNode } from '$lib/document/tree';
	import type { TreeState } from '$lib/document/tree-state.svelte';

	interface Props {
		tree: TreeState;
		/** Opens the source of a node; without it the tree shows no «Источник» buttons. */
		onopen?: (nodeId: number) => void;
	}

	let { tree, onopen }: Props = $props();

	function itemIn(list: Element | null, id: number): HTMLElement | null {
		return list?.querySelector<HTMLElement>(`[data-node-id="${id}"]`) ?? null;
	}

	/** Arrow keys, Home/End, Enter and Space on a focused node (WAI-ARIA tree pattern). */
	async function onkeydown(event: KeyboardEvent & { currentTarget: HTMLElement }, id: number) {
		// Keys typed on the node's buttons or on a nested node are not this node's business.
		if (event.target !== event.currentTarget) {
			return;
		}
		const next = tree.navigate(event.key, id);
		if (next !== null) {
			event.preventDefault();
			const list = event.currentTarget.closest('[role="tree"]');
			await tick();
			itemIn(list, next)?.focus();
		}
	}

	function select(event: MouseEvent, id: number) {
		event.stopPropagation();
		tree.selectedId = id;
	}

	/** «К пункту»: once the ancestors are expanded, bring the requested node into view and focus it. */
	function revealRequested(list: HTMLElement) {
		const request = tree.revealed;
		const item = request === null ? null : itemIn(list, request.id);
		if (item !== null) {
			const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
			item.scrollIntoView({ block: 'center', behavior: reduceMotion ? 'auto' : 'smooth' });
			item.focus({ preventScroll: true });
		}
	}
</script>

{#snippet branch(entry: TreeNode)}
	{@const node = entry.node}
	{@const hasChildren = entry.children.length > 0}
	{@const expanded = hasChildren && tree.expanded.has(node.id)}
	{@const selected = tree.selectedId === node.id}
	{@const tabindex = tree.activeId === node.id ? 0 : -1}
	{@const short = excerpt(node.text)}
	{@const fullText = tree.fullText.has(node.id)}
	<li
		role="treeitem"
		aria-level={entry.depth + 1}
		aria-expanded={hasChildren ? expanded : undefined}
		aria-selected={selected}
		{tabindex}
		data-node-id={node.id}
		class="scroll-mt-4 outline-none [&:focus-visible>div]:outline-2 [&:focus-visible>div]:outline-accent"
		onclick={(event) => select(event, node.id)}
		onkeydown={(event) => onkeydown(event, node.id)}
	>
		<div
			class={[
				'flex items-start gap-2 rounded-md px-1.5 py-1.5',
				selected ? 'bg-accent-soft' : 'hover:bg-neutral-soft',
				node.node_type === 'service' && 'text-muted opacity-70'
			]}
		>
			{#if hasChildren}
				<button
					type="button"
					tabindex="-1"
					class="mt-0.5 shrink-0 rounded text-muted hover:text-ink"
					aria-label={expanded ? 'Свернуть' : 'Развернуть'}
					onclick={() => tree.toggle(node.id)}
				>
					<svg
						viewBox="0 0 20 20"
						fill="currentColor"
						class={['size-5 transition-transform', expanded && 'rotate-90']}
						aria-hidden="true"
					>
						<path
							d="M8.22 5.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.75.75 0 0 1-1.06-1.06L11.94 10 8.22 6.28a.75.75 0 0 1 0-1.06Z"
						/>
					</svg>
				</button>
			{:else}
				<span class="size-5 shrink-0" aria-hidden="true"></span>
			{/if}

			<div class="grid min-w-0 flex-1 gap-0.5">
				<!-- Markers, places and texts can be one long word; wrap them on a phone screen. -->
				<div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 wrap-anywhere">
					{#if node.marker}
						<span class="min-w-0 font-mono text-sm font-semibold">{node.marker}</span>
					{/if}
					<span class="min-w-0 font-mono text-xs text-muted">{node.anchor}</span>
					<span class="rounded bg-neutral-soft px-1.5 text-xs text-neutral">
						{NODE_TYPE_LABELS[node.node_type]}
					</span>
				</div>
				<p
					class={[
						'text-sm wrap-anywhere whitespace-pre-line',
						(node.node_type === 'section' || node.node_type === 'heading') && 'font-semibold'
					]}
				>
					{fullText ? node.text : short.text}
					{#if short.clipped}
						<button
							type="button"
							{tabindex}
							class="ml-1 text-sm whitespace-nowrap text-accent hover:underline"
							onclick={() => tree.toggleText(node.id)}
						>
							{fullText ? 'свернуть текст' : 'показать полностью'}
						</button>
					{/if}
				</p>
			</div>

			{#if onopen}
				<button
					type="button"
					{tabindex}
					class="shrink-0 rounded bg-accent-soft px-2 py-0.5 font-mono text-xs text-accent hover:underline"
					onclick={() => onopen(node.id)}
				>
					Источник
				</button>
			{/if}
		</div>

		{#if expanded}
			<ul role="group" class="ml-4 border-l border-line pl-2">
				{#each entry.children as child (child.node.id)}
					{@render branch(child)}
				{/each}
			</ul>
		{/if}
	</li>
{/snippet}

{#if tree.tree.roots.length === 0}
	<p class="text-sm text-muted">Структура документа не извлечена.</p>
{:else}
	<div class="grid gap-2">
		<div class="flex gap-4">
			<button
				type="button"
				class="text-sm text-accent hover:underline"
				onclick={() => tree.expandAll()}
			>
				Развернуть всё
			</button>
			<button
				type="button"
				class="text-sm text-accent hover:underline"
				onclick={() => tree.collapseAll()}
			>
				Свернуть всё
			</button>
		</div>
		<ul role="tree" aria-label="Структура документа" {@attach revealRequested}>
			{#each tree.tree.roots as root (root.node.id)}
				{@render branch(root)}
			{/each}
		</ul>
	</div>
{/if}
