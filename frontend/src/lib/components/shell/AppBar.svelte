<script lang="ts">
	import { resolve } from '$app/paths';

	import ThemeToggle from './ThemeToggle.svelte';
</script>

<header class="sticky top-0 z-10 border-b border-line bg-surface">
	<div
		class="mx-auto flex min-h-14 max-w-[1080px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2"
	>
		<span class="flex items-center gap-2.5 font-semibold">
			<!-- Brand mark from prototype.html: an outlined square with its right half filled. -->
			<span
				class="relative size-[18px] shrink-0 rounded-[3px] border-2 border-accent"
				aria-hidden="true"
			>
				<span class="absolute top-[3px] right-[3px] bottom-[3px] left-1/2 bg-accent"></span>
			</span>
			Анализ оргструктуры
		</span>
		<a href={resolve('/')} class="ml-auto text-[0.9rem] text-accent hover:underline">
			Новый анализ
		</a>
		<ThemeToggle />
	</div>
</header>
