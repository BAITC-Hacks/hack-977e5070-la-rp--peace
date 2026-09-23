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
	/**
	 * «До» and «После» are one required document each (docs/spec/tz_site.md §6.1); the external
	 * sets are optional and take any number of files.
	 */
	optional: boolean;
}

export const DOC_SETS: readonly DocSetInfo[] = [
	{
		set: 'before',
		title: 'Документ «До»',
		hint: 'Редакция до реорганизации: положение о подразделении, оргструктура или штатное расписание.',
		optional: false
	},
	{
		set: 'after',
		title: 'Документ «После»',
		hint: 'Тот же документ в редакции после реорганизации.',
		optional: false
	},
	{
		set: 'regulatory',
		title: 'НПА и регулирующие документы',
		hint: 'Законы, стандарты и требования регулятора к функциям подразделений.',
		optional: true
	},
	{
		set: 'benchmark',
		title: 'Документы других операторов',
		hint: 'Оргструктуры и положения других операторов для сравнения.',
		optional: true
	}
];
