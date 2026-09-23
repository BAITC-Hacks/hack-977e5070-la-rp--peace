<script lang="ts">
	import type { DocSet } from '$lib/api/types';
	import { sourceLabel } from '$lib/source/label';
	import type { SourcePanelState, SourceTarget } from '$lib/source/panel.svelte';

	interface Props {
		panel: SourcePanelState;
		/** All citations of the finding, so the panel can page through them. */
		targets: readonly SourceTarget[];
		/** Which of `targets` this chip opens. */
		index: number;
		set: DocSet | null;
		/** Short citation, e.g. «п. 3.4». */
		anchor: string;
	}

	let { panel, targets, index, set, anchor }: Props = $props();

	const quote = $derived(targets[index]?.quote);
</script>

<button
	type="button"
	class="rounded bg-accent-soft px-2 py-0.5 text-left font-mono text-xs text-accent hover:underline"
	title={quote === undefined ? undefined : `«${quote}»`}
	aria-haspopup="dialog"
	onclick={() => panel.open(targets, index)}
>
	{sourceLabel(set, anchor)}
</button>
