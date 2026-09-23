import { ANALYSIS_TABS, type AnalysisTabId } from '$lib/analysis/tabs';

/** Name of the query parameter that keeps the open sub-page of «Анализ», e.g. `?tab=overlap`. */
export const TAB_PARAM = 'tab';

/** The sub-page named in the query; the first one for a missing or unknown name. */
export function tabFromQuery(params: URLSearchParams): AnalysisTabId {
	const name = params.get(TAB_PARAM);
	return ANALYSIS_TABS.find((tab) => tab.id === name)?.id ?? ANALYSIS_TABS[0].id;
}

/** Query that opens the sub-page `tab`, keeping the other parameters of `params`. */
export function tabQuery(params: URLSearchParams, tab: AnalysisTabId): `?${string}` {
	const next = new URLSearchParams(params);
	next.set(TAB_PARAM, tab);
	return `?${next}`;
}
