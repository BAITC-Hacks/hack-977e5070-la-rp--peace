<script lang="ts">
	import { STAGE_STATE_LABELS, type StageState } from '$lib/status/stages';

	interface Props {
		state: StageState;
	}

	let { state }: Props = $props();
</script>

<!-- The state is spelled out next to the dot, so it does not rely on colour alone. -->
<span
	class={[
		'inline-flex items-center gap-1.5 text-[0.8rem] whitespace-nowrap',
		state === 'done' ? 'text-ink' : state === 'failed' ? 'font-medium text-bad' : 'text-muted'
	]}
>
	<span
		aria-hidden="true"
		class={[
			'inline-block size-[9px] shrink-0 rounded-full border-[1.5px]',
			state === 'waiting' && 'border-line',
			state === 'done' && 'border-ok bg-ok',
			state === 'failed' && 'border-bad bg-bad',
			state === 'running' &&
				'animate-spin border-accent border-t-transparent motion-reduce:animate-none motion-reduce:bg-accent'
		]}
	></span>
	{STAGE_STATE_LABELS[state]}
</span>
