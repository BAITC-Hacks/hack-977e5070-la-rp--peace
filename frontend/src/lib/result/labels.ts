// Russian labels of the «Изменения → Визуал» screen, as in docs/spec/visual_compare.html.

import type { Confidence, DocSide, FindingType, ItemStatus, Verdict } from './types';

/** Finding types in the order of tech task §5.2; summary counters follow it. */
export const FINDING_TYPES: readonly FindingType[] = [
	'kept',
	'transformed',
	'created',
	'abolished',
	'moved',
	'loss',
	'duplication',
	'conflict',
	'contradiction',
	'overlap'
];

export const TYPE_LABELS: Record<FindingType, string> = {
	kept: 'Сохранено',
	transformed: 'Преобразовано',
	created: 'Создано',
	abolished: 'Упразднено',
	moved: 'Перенесено',
	loss: 'Потеря функции',
	duplication: 'Дублирование',
	conflict: 'Конфликт интересов',
	contradiction: 'Противоречие функций',
	overlap: 'Пересечение зон'
};

export const STATUS_LABELS: Record<ItemStatus, string> = {
	kept: 'сохранено',
	transformed: 'преобразовано',
	created: 'создано',
	abolished: 'упразднено',
	moved: 'перенесено',
	loss: 'потеряна'
};

export const CONFIDENCE_LABELS: Record<Confidence, string> = {
	high: 'высокая',
	medium: 'средняя',
	low: 'низкая'
};

/** Name of a document version, e.g. «Документ «до»». */
export const DOC_LABELS: Record<DocSide, string> = {
	before: 'Документ «до»',
	after: 'Документ «после»'
};

/** Badge on a card the employee has checked. */
export const VERDICT_LABELS: Record<Verdict, string> = {
	ok: '✓ подтверждено',
	no: '✕ отклонено'
};

export const VERDICT_ACTIONS: Record<Verdict, string> = {
	ok: '✓ Подтвердить',
	no: '✕ Отклонить'
};

/** Next to a loss: the function has no owner after the reorganisation. */
export const LOSS_MARK = '∅ не закреплено';

/** Marks an evidence step that is the agent's reasoning rather than a quoted fact (I3). */
export const INFERENCE_LABEL = 'рассуждение агента';

/** Shown with every finding (I6). */
export const DISCLAIMER =
	'Вывод носит рекомендательный характер и требует проверки ответственным сотрудником.';

const scoreFormat = new Intl.NumberFormat('ru-RU', {
	minimumFractionDigits: 2,
	maximumFractionDigits: 2
});

/** Similarity or threshold with two decimals, e.g. «0,75». */
export function formatScore(value: number): string {
	return scoreFormat.format(value);
}
