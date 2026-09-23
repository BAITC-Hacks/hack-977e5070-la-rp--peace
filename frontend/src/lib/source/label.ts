import type { DocSet } from '$lib/api/types';

/** Short side names for source chips and the source panel. */
export const SET_LABELS: Record<DocSet, string> = {
	before: 'До',
	after: 'После',
	regulatory: 'НПА',
	benchmark: 'Другой оператор'
};

/** Chip text such as «До · п. 3.4»; a part that is unknown is left out. */
export function sourceLabel(set: DocSet | null, anchor: string): string {
	const parts = [set === null ? '' : SET_LABELS[set], anchor.trim()].filter((part) => part !== '');
	return parts.length > 0 ? parts.join(' · ') : 'Источник';
}
