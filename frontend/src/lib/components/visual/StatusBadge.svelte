<script lang="ts">
	import '$lib/result/colors.css';
	import { STATUS_LABELS } from '$lib/result/labels';
	import type { ItemStatus } from '$lib/result/types';

	interface Props {
		status: ItemStatus;
	}

	let { status }: Props = $props();
</script>

<!-- Tint of the type colour; the text is mixed towards --ink to stay readable in both themes. -->
<span
	class="rounded-full bg-(--c)/15 px-2 py-0.5 text-xs whitespace-nowrap text-[color:color-mix(in_srgb,var(--c)_70%,var(--ink))]"
	style:--c={`var(--${status})`}
>
	{STATUS_LABELS[status]}
</span>
