<script lang="ts">
	import type { Attachment } from 'svelte/attachments';

	import { STAGES, documentErrors, overallStatus, type DocumentProgress } from '$lib/status/stages';

	import StageCell from './StageCell.svelte';

	interface Props {
		/** One row per document, in the order to list them. */
		rows: readonly DocumentProgress[];
		/** Called once, «Готово» having been on screen for a moment, to open the results. */
		ondone: () => void;
		/** What happens next, shown after «Готово.». */
		doneText?: string;
	}

	let { rows, ondone, doneText = 'Запускаю анализ…' }: Props = $props();

	/** How long «Готово» stays on screen before `ondone`. */
	const DONE_DELAY_MS = 1200;
	const COLUMNS = ['Документ', ...STAGES.map((stage) => stage.label)];

	const status = $derived(overallStatus(rows));
	const errors = $derived(documentErrors(rows));
	let notified = false;

	/**
	 * Attached to the «Готово» notice: calls `ondone` once the notice has been shown for
	 * DONE_DELAY_MS. The notice goes away when the rows stop being done or the screen is left,
	 * and that cancels the call; after the first call there is never a second one.
	 */
	const openResultsLater: Attachment = () => {
		if (notified) {
			return;
		}
		const timer = setTimeout(() => {
			notified = true;
			ondone();
		}, DONE_DELAY_MS);
		return () => clearTimeout(timer);
	};
</script>

<div class="grid grid-cols-1 gap-5">
	<div class="grid gap-1.5">
		<h1 class="text-2xl font-semibold text-balance">Обработка документов</h1>
		<p class="text-muted">
			Анализ выполняется один раз. Дальше страницы показывают готовый результат.
		</p>
	</div>

	<div class="overflow-x-auto rounded-lg border border-line bg-surface">
		<table class="w-full min-w-[560px] border-collapse text-left">
			<thead class="border-b border-line">
				<tr>
					{#each COLUMNS as column (column)}
						<th
							scope="col"
							class="px-3 py-2.5 text-xs font-medium tracking-[0.07em] text-muted uppercase"
						>
							{column}
						</th>
					{/each}
				</tr>
			</thead>
			<tbody class="divide-y divide-line">
				<!-- Rows hold no state of their own, so their position is all that identifies them. -->
				{#each rows as row, index (index)}
					<tr>
						<th scope="row" class="px-3 py-2.5 align-top font-normal wrap-anywhere">{row.label}</th>
						{#each STAGES as stage (stage.id)}
							<td class="px-3 py-2.5 align-top"><StageCell state={row.stages[stage.id]} /></td>
						{/each}
					</tr>
				{:else}
					<tr>
						<td colspan={STAGES.length + 1} class="px-3 py-2.5 text-muted">
							Ждём список документов…
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	{#if errors.length > 0}
		<div
			role="alert"
			class="grid gap-1 rounded-lg border border-bad bg-bad-soft px-4 py-3 text-bad"
		>
			<p class="font-semibold">Ошибка обработки</p>
			<ul class="grid gap-1">
				{#each errors as error, index (index)}
					<li class="wrap-anywhere">
						<span class="font-medium">{error.label}</span> — {error.message}
					</li>
				{/each}
			</ul>
		</div>
	{/if}

	{#if status === 'done'}
		<p role="status" {@attach openResultsLater}>
			<strong class="font-semibold">Готово.</strong>
			<span class="text-muted">{doneText}</span>
		</p>
	{/if}
</div>
