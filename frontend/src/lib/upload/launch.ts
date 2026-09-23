import type { UploadItem } from './session.svelte';

/** The sets an analysis cannot run without (docs/spec/tz_site.md §6.1). */
const REQUIRED = [
	{ set: 'before', label: '«До»' },
	{ set: 'after', label: '«После»' }
] as const;

/**
 * Why «Начать анализ» is not available yet, or `null` once it is. Files still uploading or being
 * parsed do not block the start: the status screen follows them to the end.
 */
export function launchBlocker(items: readonly UploadItem[]): string | null {
	const missing = REQUIRED.filter(({ set }) => !items.some((item) => item.set === set));
	if (missing.length > 0) {
		const labels = missing.map(({ label }) => label).join(' и ');
		return `Загрузите ${missing.length > 1 ? 'документы' : 'документ'} ${labels}.`;
	}
	const failed = items.find((item) => item.status === 'failed');
	if (failed) {
		if (failed.documentId !== null) {
			return `Не удалось получить статус файла «${failed.name}»: повторите запрос или удалите его.`;
		}
		return `Файл «${failed.name}» не загружен: повторите загрузку или удалите его.`;
	}
	const broken = items.find((item) => (item.document?.blocking_issues ?? 0) > 0);
	if (broken) {
		return `В файле «${broken.name}» есть блокирующие проблемы разбора: удалите его или загрузите другой.`;
	}
	return null;
}
