import type { NodeType, ParseStatus } from '$lib/api/document';
import type { DocSet } from '$lib/api/types';

export const PARSE_STATUS_LABELS: Record<ParseStatus, string> = {
	pending: 'Разбирается',
	parsed: 'Разобран',
	needs_review: 'Требует проверки',
	validated: 'Проверен'
};

export const DOC_SET_LABELS: Record<DocSet, string> = {
	before: '«До»',
	after: '«После»',
	regulatory: 'НПА',
	benchmark: 'Другой оператор'
};

export const NODE_TYPE_LABELS: Record<NodeType, string> = {
	section: 'раздел',
	clause: 'пункт',
	heading: 'заголовок',
	list: 'список',
	list_item: 'подпункт',
	table: 'таблица',
	table_row: 'строка таблицы',
	table_cell: 'ячейка',
	text: 'абзац',
	service: 'служебный'
};

/** Backend `IssueType` values; `issueTypeLabel` shows unknown types as they are. */
const ISSUE_TYPE_LABELS: Record<string, string> = {
	empty_content: 'Пустой текст',
	ambiguous_boundary: 'Неясная граница пункта',
	ambiguous_parent: 'Неясная вложенность',
	numbering_gap: 'Пропуск в нумерации',
	uncovered_text: 'Текст вне структуры',
	other: 'Другое'
};

export function issueTypeLabel(issueType: string): string {
	return Object.hasOwn(ISSUE_TYPE_LABELS, issueType) ? ISSUE_TYPE_LABELS[issueType] : issueType;
}
