import type { DocSet } from './api/types';

/**
 * Suggestions for the document type field. The backend stores the type as free text read from
 * the document, so these only speed up typing the common kinds (.agents/frontend.md §2.1).
 */
export const DOC_TYPE_SUGGESTIONS: readonly string[] = [
	'Оргструктура',
	'Положение о подразделении',
	'Должностная инструкция',
	'Распорядительный документ',
	'ВНД'
];

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
