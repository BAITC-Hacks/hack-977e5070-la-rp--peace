import type { AnalysesApi } from '$lib/api/client';
import { describeError } from '$lib/api/errors';

import type { UploadItem } from './session.svelte';

/** The sets an analysis cannot run without (docs/spec/tz_site.md §6.1). */
const REQUIRED = [
	{ set: 'before', label: '«До»' },
	{ set: 'after', label: '«После»' }
] as const;

/** Why the analysis cannot start yet, or `null` once every file is parsed and usable. */
export function launchBlocker(items: readonly UploadItem[]): string | null {
	const missing = REQUIRED.filter(({ set }) => !items.some((item) => item.set === set));
	if (missing.length > 0) {
		const labels = missing.map(({ label }) => label).join(' и ');
		return `Загрузите ${missing.length > 1 ? 'документы' : 'документ'} ${labels}.`;
	}
	if (items.some((item) => item.status === 'uploading' || item.status === 'parsing')) {
		return 'Дождитесь окончания разбора.';
	}
	const failed = items.find((item) => item.status === 'failed');
	if (failed) {
		return `Файл «${failed.file.name}» не загружен: повторите загрузку или удалите его.`;
	}
	const broken = items.find((item) => (item.document?.blocking_issues ?? 0) > 0);
	if (broken) {
		return `В файле «${broken.file.name}» есть блокирующие проблемы разбора: удалите его или загрузите другой.`;
	}
	return null;
}

/** Every parsed document of every set, in the order the files were added. */
export function analysisDocumentIds(items: readonly UploadItem[]): number[] {
	return items.flatMap((item) => (item.parsed && item.document ? [item.document.id] : []));
}

/** Default name of a run, e.g. «Анализ от 23.09.2026, 16:05» (.agents/frontend.md §2.1). */
export function analysisName(now: Date | number): string {
	const when = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' });
	return `Анализ от ${when.format(now)}`;
}

/** The «Начать анализ» action of the upload screen. */
export class AnalysisLauncher {
	/** A start request is in flight, or it succeeded and the page is navigating away. */
	starting = $state(false);
	error = $state<string | null>(null);
	readonly #api: AnalysesApi;

	constructor(api: AnalysesApi) {
		this.#api = api;
	}

	/** Starts the analysis on the uploaded files; resolves to its id, or `null` if it did not start. */
	async start(
		items: readonly UploadItem[],
		now: Date | number = Date.now()
	): Promise<number | null> {
		if (this.starting || launchBlocker(items) !== null) {
			return null;
		}
		this.starting = true;
		this.error = null;
		try {
			const analysis = await this.#api.start(analysisName(now), analysisDocumentIds(items));
			return analysis.id;
		} catch (error) {
			this.error = describeError(error);
			this.starting = false;
			return null;
		}
	}
}
