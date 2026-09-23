// Model of the «Обработка документов» screen (docs/spec/tz_site.md §6.2, P0.1): every document
// passes the same stages, one table column each, as in docs/spec/prototype.html.

export type StageId = 'uploaded' | 'parsed' | 'segmented';

export interface Stage {
	id: StageId;
	/** Column heading. */
	label: string;
}

/**
 * Stages in the order a document passes them. The prototype's «Проанализирован» comes back once
 * the backend compares documents; until then the screen shows only what really happens.
 */
export const STAGES: readonly Stage[] = [
	{ id: 'uploaded', label: 'Загружен' },
	{ id: 'parsed', label: 'Распознан' },
	{ id: 'segmented', label: 'Разбит на блоки' }
];

export type StageState = 'waiting' | 'running' | 'done' | 'failed';

export const STAGE_STATE_LABELS: Record<StageState, string> = {
	waiting: 'ждёт',
	running: 'в работе',
	done: 'готово',
	failed: 'ошибка'
};

/** One table row: a document and how far it has got. */
export interface DocumentProgress {
	/** Which document, e.g. «До: Положение_2024.docx». */
	label: string;
	stages: Record<StageId, StageState>;
	/** Why processing stopped, as the backend reports it; null while nothing went wrong. */
	error: string | null;
}

/** Where processing of all documents stands. */
export type OverallStatus = 'running' | 'done' | 'failed';

/** A document that failed, with the message to show for it. */
export interface DocumentError {
	label: string;
	message: string;
}

/** The first stage of the document that failed, or null if none did. */
export function failedStage(row: DocumentProgress): Stage | null {
	return STAGES.find((stage) => row.stages[stage.id] === 'failed') ?? null;
}

/** What went wrong with the document, naming the failed stage when known; null if nothing did. */
export function errorMessage(row: DocumentProgress): string | null {
	const stage = failedStage(row);
	const reason = row.error?.trim() ?? '';
	if (reason !== '') {
		return stage === null ? reason : `Этап «${stage.label}»: ${reason}`;
	}
	return stage === null ? null : `Этап «${stage.label}» завершился с ошибкой.`;
}

/** Every failed document, in table order. */
export function documentErrors(rows: readonly DocumentProgress[]): DocumentError[] {
	return rows.flatMap((row) => {
		const message = errorMessage(row);
		return message === null ? [] : [{ label: row.label, message }];
	});
}

/**
 * `failed` as soon as any document has failed, `done` only once every stage of every document is
 * done, `running` otherwise — including while there are no documents yet.
 */
export function overallStatus(rows: readonly DocumentProgress[]): OverallStatus {
	if (rows.some((row) => errorMessage(row) !== null)) {
		return 'failed';
	}
	const allDone =
		rows.length > 0 &&
		rows.every((row) => STAGES.every((stage) => row.stages[stage.id] === 'done'));
	return allDone ? 'done' : 'running';
}
