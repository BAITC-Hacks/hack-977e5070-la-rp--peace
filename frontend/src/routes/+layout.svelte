<script lang="ts">
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import { resolve } from '$app/paths';

	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<div class="min-h-screen bg-slate-50 text-slate-900">
	<header class="border-b border-slate-200 bg-white">
		<div
			class="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-6 py-3"
		>
			<a href={resolve('/')} class="font-semibold">Анализ оргструктуры и функционала</a>
			<p
				class="rounded-full bg-amber-50 px-3 py-1 text-xs text-amber-900 ring-1 ring-amber-200"
				role="note"
			>
				Выводы ИИ носят рекомендательный характер и требуют проверки ответственным сотрудником
			</p>
		</div>
	</header>
	<main class="mx-auto max-w-6xl px-6 py-8">
		{@render children()}
	</main>
</div>
