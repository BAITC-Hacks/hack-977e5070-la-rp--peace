<script lang="ts">
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import { page } from '$app/state';
	import AppBar from '$lib/components/shell/AppBar.svelte';

	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	// prototype.html shows the top bar on result pages only; the upload screen goes without it.
	const showAppBar = $derived(page.route.id !== '/');
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

{#if showAppBar}
	<AppBar />
{/if}

<main class="mx-auto max-w-[1080px] px-4 pt-7 pb-16">
	{@render children()}
</main>
