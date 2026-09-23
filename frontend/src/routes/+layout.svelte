<script lang="ts">
	import { onMount } from 'svelte';
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import { page } from '$app/state';
	import AppBar from '$lib/components/shell/AppBar.svelte';
	import { uploadSession } from '$lib/upload/current';

	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	onMount(() => {
		void uploadSession.restore();
	});

	// prototype.html shows the top bar on result pages only, not on the upload and status screens.
	const showAppBar = $derived(page.route.id !== '/' && page.route.id !== '/status');
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

{#if showAppBar}
	<AppBar />
{/if}

<main class="mx-auto max-w-[1080px] px-4 pt-7 pb-16">
	{@render children()}
</main>
