// Top menu of the results screens (tz_site.md §6): «Изменения · Анализ · Чат».

export type ResultsSectionId = 'changes' | 'analysis' | 'chat';

export interface ResultsSection {
	id: ResultsSectionId;
	label: string;
	/** False for a section that has no page yet; it is shown in the menu, but inactive. */
	enabled: boolean;
}

export const RESULTS_SECTIONS: readonly ResultsSection[] = [
	{ id: 'changes', label: 'Изменения', enabled: true },
	{ id: 'analysis', label: 'Анализ', enabled: true },
	// P2: the chat gets its page once P0 and P1 are done (tz_site.md §8).
	{ id: 'chat', label: 'Чат', enabled: false }
];

const ROUTE_SECTIONS: Record<string, ResultsSectionId> = {
	'/analyses/[id]/changes': 'changes',
	'/analyses/[id]/analysis': 'analysis'
};

/** The section a route of the results screens belongs to; null for any other route. */
export function sectionOfRoute(routeId: string | null): ResultsSectionId | null {
	return routeId === null ? null : (ROUTE_SECTIONS[routeId] ?? null);
}
