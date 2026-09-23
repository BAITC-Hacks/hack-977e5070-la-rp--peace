<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import { compareQuery } from '$lib/diff/anchor';
	import { SET_LABELS } from '$lib/source/label';
	import { uploadSession } from '$lib/upload/current';
	import { comparePair, parsedDocuments } from '$lib/upload/parsed';

	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	/** The documents of the analysis being prepared; empty after a reload, as the list is in memory. */
	const documents = $derived(parsedDocuments(uploadSession.items));
	/** «До» and «После» for the Word view, once both are parsed. */
	const pair = $derived(comparePair(documents));
</script>

{#if documents.length > 1}
	<nav aria-label="Документы анализа" class="mb-5 flex flex-wrap gap-2">
		{#each documents as doc (doc.id)}
			<a
				href={resolve('/documents/[id]', { id: String(doc.id) })}
				aria-current={page.params.id === String(doc.id) ? 'page' : undefined}
				class="max-w-full truncate rounded-md border border-line bg-surface px-3 py-1.5 text-[0.9rem] hover:border-accent aria-[current=page]:border-accent aria-[current=page]:bg-accent aria-[current=page]:text-accent-ink"
			>
				{SET_LABELS[doc.set]} · {doc.name}
			</a>
		{/each}
		{#if pair !== null}
			<a
				href={resolve(`/compare${compareQuery(pair.before, pair.after)}`)}
				class="rounded-md border border-accent px-3 py-1.5 text-[0.9rem] text-accent hover:bg-accent-soft"
			>
				Сравнить редакции
			</a>
		{/if}
	</nav>
{/if}

{@render children()}
