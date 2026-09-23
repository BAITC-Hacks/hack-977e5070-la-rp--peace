// Stages of the analysis run on the status screen (docs/spec/tz_site.md §6.2,
// .agents/frontend.md §2.2), shown once the documents have been parsed.

import type { AnalysisStageOut, AnalysisStageStatus } from '$lib/api/analyses';

import type { StageState } from './stages';

/**
 * The seven stages of .agents/frontend.md §2.2, in the order they run. They are shown until the
 * backend reports its own stages, whose names it sends ready to display (.agents/backend.md §3).
 */
export const ANALYSIS_STAGE_NAMES: readonly string[] = [
	'Разбор документов',
	'Подразделения',
	'Сопоставление до/после',
	'Сравнение функций',
	'Потери функций',
	'Дублирование и конфликты',
	'Заключение'
];

/** The stages before the backend has reported any: all pending. */
export function initialStages(): AnalysisStageOut[] {
	return ANALYSIS_STAGE_NAMES.map((name, order) => ({ name, order, status: 'pending' }));
}

/**
 * `stages` with `update` applied: a stage of the same name takes the new status, a new one joins
 * the list; the result is sorted by `order`.
 */
export function mergeStages(
	stages: readonly AnalysisStageOut[],
	update: readonly AnalysisStageOut[]
): AnalysisStageOut[] {
	const byName = new Map(stages.map((stage) => [stage.name, stage]));
	for (const stage of update) {
		byName.set(stage.name, stage);
	}
	return [...byName.values()].sort((a, b) => a.order - b.order);
}

/** The backend's stage status as the status screen names it: `pending` is «ждёт». */
export function stageState(status: AnalysisStageStatus): StageState {
	return status === 'pending' ? 'waiting' : status;
}

/** Default name of a run, as .agents/frontend.md §2.1 proposes it. */
export function defaultAnalysisName(now: Date): string {
	return `Анализ от ${now.toLocaleDateString('ru-RU')}`;
}

/** «14:03:27» for an ISO timestamp of the agent log; the raw value if it cannot be read. */
export function logTime(at: string): string {
	const time = new Date(at);
	if (Number.isNaN(time.getTime())) {
		return at;
	}
	return time.toLocaleTimeString('ru-RU', {
		hour: '2-digit',
		minute: '2-digit',
		second: '2-digit'
	});
}
