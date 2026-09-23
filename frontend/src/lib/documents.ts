import type { DocSet, DocType } from './api/types';

/** Document types in the order the type select lists them. */
export const DOC_TYPES: readonly DocType[] = [
	'org_structure',
	'unit_regulation',
	'job_description',
	'order',
	'internal_regulation',
	'unknown'
];

export const DOC_TYPE_LABELS: Record<DocType, string> = {
	org_structure: 'Оргструктура',
	unit_regulation: 'Положение о подразделении',
	job_description: 'Должностная инструкция',
	order: 'Распорядительный документ',
	internal_regulation: 'ВНД',
	unknown: 'Не определено'
};

/** Narrows an arbitrary string (e.g. a `<select>` value) to a known document type. */
export function isDocType(value: string): value is DocType {
	return (DOC_TYPES as readonly string[]).includes(value);
}

export interface DocSetInfo {
	set: DocSet;
	title: string;
	hint: string;
	/** Both «before» and «after» need documents; the other sets are optional (tech task §8). */
	optional: boolean;
}

export const DOC_SETS: readonly DocSetInfo[] = [
	{
		set: 'before',
		title: 'До реорганизации',
		hint: 'Оргструктура, положения о подразделениях, должностные инструкции и распорядительные документы до изменений.',
		optional: false
	},
	{
		set: 'after',
		title: 'После реорганизации',
		hint: 'Те же виды документов в редакции после изменений.',
		optional: false
	},
	{
		set: 'regulatory',
		title: 'Нормативные требования',
		hint: 'Законы, стандарты и регуляторные требования, которым должны соответствовать функции подразделений.',
		optional: true
	},
	{
		set: 'benchmark',
		title: 'Бенчмаркинг',
		hint: 'Организационные структуры других операторов для сравнения.',
		optional: true
	}
];
