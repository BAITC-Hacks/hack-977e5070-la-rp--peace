// Sub-pages of «Анализ» (tech task §6.5, P1.1): each lists the findings of its types.

import type { Finding, FindingType } from '$lib/result/types';

export type AnalysisTabId = 'loss' | 'duplication' | 'conflict' | 'overlap';

export interface AnalysisTab {
	id: AnalysisTabId;
	label: string;
	/** Finding types the sub-page lists, in the order of their labels. */
	types: readonly FindingType[];
	/** Shown when the sub-page has no findings. */
	empty: string;
}

export const ANALYSIS_TABS: readonly AnalysisTab[] = [
	{ id: 'loss', label: 'Потеря функций', types: ['loss'], empty: 'Потерь функций не найдено' },
	{
		id: 'duplication',
		label: 'Дублирование',
		types: ['duplication'],
		empty: 'Дублирований не найдено'
	},
	{
		id: 'conflict',
		label: 'Конфликт интересов',
		types: ['conflict', 'contradiction'],
		empty: 'Конфликтов интересов и противоречий функций не найдено'
	},
	{
		id: 'overlap',
		label: 'Пересечение зон',
		types: ['overlap'],
		empty: 'Пересечений зон не найдено'
	}
];

/** The findings the sub-page lists, in result order. Pass only findings that may be shown (I1). */
export function tabFindings(findings: readonly Finding[], tab: AnalysisTab): Finding[] {
	return findings.filter((finding) => tab.types.includes(finding.type));
}

/**
 * Index of the tab a key moves to in a tab list of `count` tabs (WAI-ARIA tabs pattern): arrows
 * wrap around, Home and End jump to the ends. Null for any other key.
 */
export function tabAfterKey(key: string, index: number, count: number): number | null {
	switch (key) {
		case 'ArrowRight':
			return (index + 1) % count;
		case 'ArrowLeft':
			return (index - 1 + count) % count;
		case 'Home':
			return 0;
		case 'End':
			return count - 1;
		default:
			return null;
	}
}
