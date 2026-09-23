<script lang="ts">
	import '$lib/result/colors.css';
	import {
		CONFIDENCE_LABELS,
		DISCLAIMER,
		DOC_LABELS,
		INFERENCE_LABEL,
		TYPE_LABELS,
		VERDICT_ACTIONS,
		formatScore
	} from '$lib/result/labels';
	import type { ReviewState } from '$lib/result/review.svelte';
	import type { Confidence, Finding, Source, Verdict } from '$lib/result/types';

	interface Props {
		/** The finding to show; null closes the panel. */
		finding: Finding | null;
		review: ReviewState;
		/** The panel was closed (×, Esc or a click outside it); set `finding` to null. */
		onclose: () => void;
		/** A quote was clicked: show it in the document. */
		onquote: (source: Source) => void;
	}

	let { finding, review, onclose, onquote }: Props = $props();

	const headingId = $props.id();
	const verdicts: readonly Verdict[] = ['ok', 'no'];
	const confidenceClass: Record<Confidence, string> = {
		high: 'bg-ok-soft text-ok',
		medium: 'bg-warn-soft text-warn',
		low: 'bg-bad-soft text-bad'
	};

	function sync(dialog: HTMLDialogElement) {
		if (finding !== null && !dialog.open) {
			dialog.showModal();
		} else if (finding === null && dialog.open) {
			dialog.close();
		}
	}
</script>

{#snippet heading(text: string)}
	<h3 class="mb-2 text-xs font-semibold tracking-[0.08em] text-muted uppercase">{text}</h3>
{/snippet}

{#snippet quote(source: Source)}
	<button
		type="button"
		class="mt-1.5 block w-full rounded-md border border-line bg-page px-2.5 py-2 text-left text-[13px] hover:border-accent"
		onclick={() => onquote(source)}
	>
		<span class="block text-xs text-muted">
			<b class="font-semibold text-accent">{DOC_LABELS[source.doc]}</b> · {source.block} · {source.clause}
			— показать в документе
		</span>
		<q class="mt-0.5 block italic">{source.quote}</q>
	</button>
{/snippet}

<dialog
	class="m-0 ml-auto h-dvh max-h-dvh w-[min(560px,100%)] max-w-full border-l border-line bg-surface text-ink backdrop:bg-black/45"
	aria-labelledby={headingId}
	closedby="any"
	{onclose}
	{@attach sync}
>
	{#if finding}
		{@const evidence = finding.evidence}
		{@const verdict = review.verdictOf(finding.id)}
		<div class="relative grid gap-5 px-6 pt-5 pb-10" style:--c={`var(--${finding.type})`}>
			<form method="dialog" class="absolute top-3 right-4">
				<button
					class="rounded px-1.5 text-2xl leading-none text-muted hover:text-ink"
					aria-label="Закрыть"
				>
					×
				</button>
			</form>

			<header class="grid gap-1 pr-8">
				<p class="text-[13px] font-semibold text-(--c)">
					{TYPE_LABELS[finding.type]} · {finding.id}
				</p>
				<h2 id={headingId} class="text-lg font-semibold text-balance">{evidence.conclusion}</h2>
			</header>

			<section>
				{@render heading('Как получен вывод')}
				<p class="text-sm text-muted">{evidence.method}</p>
			</section>

			<section>
				{@render heading('Цепочка доказательств')}
				<ol class="grid">
					{#each evidence.steps as step, index (index)}
						<li class="ml-1 border-l-2 border-line pb-2.5 pl-3">
							<p class="text-xs text-muted">Шаг {index + 1}</p>
							<p class="text-sm">
								{#if step.kind === 'inference'}
									<span class="mr-1.5 rounded bg-neutral-soft px-1.5 text-[11px] text-neutral">
										{INFERENCE_LABEL}
									</span>
								{/if}
								{step.text}
							</p>
							{#each step.sources as source, sourceIndex (sourceIndex)}
								{@render quote(source)}
							{/each}
						</li>
					{/each}
				</ol>
			</section>

			{#if evidence.checked}
				{@const checked = evidence.checked}
				<section>
					{@render heading('Что проверено')}
					<p class="mb-1.5 text-sm text-muted">
						{checked.scope}. Порог совпадения: {formatScore(checked.threshold)}.
						{checked.candidates.length > 0
							? 'Ближайшие кандидаты:'
							: 'Похожих кандидатов не найдено.'}
					</p>
					{#if checked.candidates.length > 0}
						<table class="w-full text-[13px]">
							<thead class="text-left text-muted">
								<tr class="border-b border-line">
									<th class="px-1.5 py-1 font-semibold">Кандидат</th>
									<th class="px-1.5 py-1 font-semibold">Пункт</th>
									<th class="w-[30%] px-1.5 py-1 font-semibold" colspan="2">Сходство</th>
								</tr>
							</thead>
							<tbody>
								{#each checked.candidates as candidate, candidateIndex (candidateIndex)}
									<tr class="border-b border-line">
										<td class="px-1.5 py-1">{candidate.label}</td>
										<td class="px-1.5 py-1">{candidate.clause}</td>
										<td class="px-1.5 py-1">
											<div class="relative h-1.5 rounded-sm bg-neutral-soft">
												<span
													class="absolute inset-y-0 left-0 rounded-sm bg-muted"
													style:width="{Math.min(Math.max(candidate.score, 0), 1) * 100}%"
												></span>
											</div>
										</td>
										<td class="px-1.5 py-1 text-right tabular-nums">
											{formatScore(candidate.score)}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					{/if}
				</section>
			{/if}

			{#if evidence.npa}
				<section>
					{@render heading('Нормативная база')}
					<p class="text-sm text-muted">{evidence.npa}</p>
				</section>
			{/if}

			<section>
				{@render heading('Уверенность')}
				<span
					class={[
						'inline-block rounded-full px-2.5 py-0.5 text-[13px] font-semibold',
						confidenceClass[evidence.confidence]
					]}
				>
					{CONFIDENCE_LABELS[evidence.confidence]}
				</span>
				{#if evidence.confidence_note}
					<p class="mt-1.5 text-sm text-muted">{evidence.confidence_note}</p>
				{/if}
			</section>

			<section>
				{@render heading('Проверка сотрудником')}
				<div class="flex gap-2">
					{#each verdicts as option (option)}
						<button
							type="button"
							aria-pressed={verdict === option}
							class={[
								'flex-1 rounded-md border p-2 font-medium',
								verdict === option
									? option === 'ok'
										? 'border-ok bg-ok-soft text-ok'
										: 'border-bad bg-bad-soft text-bad'
									: 'border-line bg-page hover:border-muted'
							]}
							onclick={() => review.toggle(finding.id, option)}
						>
							{VERDICT_ACTIONS[option]}
						</button>
					{/each}
				</div>
			</section>

			<p class="text-xs text-muted">{DISCLAIMER}</p>
		</div>
	{/if}
</dialog>
