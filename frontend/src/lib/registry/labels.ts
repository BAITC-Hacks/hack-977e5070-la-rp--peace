import type {
	ActivityType,
	ExtractionStatus,
	Participation,
	ReviewStatus
} from '$lib/api/registries';

export const STAGE_LABELS: Record<ExtractionStatus, string> = {
	not_started: 'Обработка ещё не начата',
	running: 'Обработка не завершена',
	done: 'Обработка завершена',
	needs_review: 'Требуется проверка',
	failed: 'Обработка завершилась с ошибкой'
};
export const REVIEW_LABELS: Record<ReviewStatus, string> = {
	pending: 'Ожидает технической проверки',
	checked: 'Технически проверено',
	needs_review: 'Требуется проверка'
};
export const ACTIVITY_LABELS: Record<ActivityType, string> = {
	goal: 'Цель',
	task: 'Задача',
	function: 'Функция',
	duty: 'Обязанность',
	right: 'Право',
	prohibition: 'Запрет',
	other: 'Другое'
};
export const PARTICIPATION_LABELS: Record<Participation, string> = {
	individual: 'Индивидуально',
	each: 'Каждый самостоятельно',
	joint: 'Совместно',
	alternative: 'Альтернативные исполнители',
	unclear: 'Участие не установлено'
};
export const CATEGORY_LABELS: Record<string, string> = {
	organization: 'Организация',
	governing_body: 'Орган управления',
	block: 'Блок',
	department: 'Департамент',
	division: 'Подразделение',
	group: 'Группа',
	position: 'Должность',
	collective: 'Коллектив',
	other: 'Другое',
	unclear: 'Категория не установлена'
};
export const RELATION_LABELS: Record<string, string> = {
	functional_subordination: 'Функциональное подчинение',
	administrative_management: 'Административное управление',
	reports_to: 'Отчётность',
	membership: 'Участие в составе',
	other: 'Другая связь'
};
export const BLOCK_LABELS = {
	found: 'Записи найдены',
	none: 'Записей нет',
	needs_clarification: 'Требуется уточнение',
	failed: 'Ошибка'
};
export const SUPPORT_LABELS: Record<string, string> = {
	name: 'название',
	alias: 'сокращение',
	aliases: 'сокращения',
	type: 'тип',
	entity_type: 'тип объекта',
	category: 'категория',
	parent: 'принадлежность',
	role: 'роль',
	roles: 'роли',
	level: 'уровень',
	position_type: 'тип должности',
	relation: 'связь',
	same_entity: 'идентичность объекта',
	formulation: 'формулировка',
	entity: 'исполнитель',
	membership: 'состав группы',
	condition: 'условие',
	deadline: 'срок',
	periodicity: 'периодичность',
	participation: 'участие',
	specificity: 'конкретность'
};
