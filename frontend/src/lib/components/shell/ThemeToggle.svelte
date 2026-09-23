<script lang="ts">
	import {
		THEME_CHOICES,
		THEME_LABELS,
		applyTheme,
		browserStorage,
		readTheme,
		saveTheme,
		type ThemeChoice
	} from '$lib/theme';

	const storage = browserStorage();
	let choice = $state<ThemeChoice>(readTheme(storage));

	function choose(next: ThemeChoice) {
		choice = next;
		saveTheme(storage, next);
		applyTheme(document.documentElement, next);
	}
</script>

<div
	role="group"
	aria-label="Тема оформления"
	class="flex divide-x divide-line overflow-hidden rounded-md border border-line text-sm"
>
	{#each THEME_CHOICES as option (option)}
		<button
			type="button"
			aria-pressed={choice === option}
			class={[
				'px-2.5 py-1 transition-colors',
				choice === option ? 'bg-accent text-accent-ink' : 'bg-surface text-muted hover:text-ink'
			]}
			onclick={() => choose(option)}
		>
			{THEME_LABELS[option]}
		</button>
	{/each}
</div>
