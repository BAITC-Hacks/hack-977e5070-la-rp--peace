<script lang="ts">
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';

	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<!-- The top menu belongs to the result pages only; upload and status go without it (prototype.html). -->
<main class="mx-auto max-w-[1080px] px-4 pt-7 pb-16">
	{@render children()}
</main>
