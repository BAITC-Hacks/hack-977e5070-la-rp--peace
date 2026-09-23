import type { IssueOut } from '$lib/api/document';

function rank(issue: IssueOut): number {
	if (issue.resolved_at !== null) {
		return 2;
	}
	return issue.is_blocking ? 0 : 1;
}

/** Open blocking issues first, then open warnings, then resolved ones; backend order within each. */
export function sortIssues(issues: readonly IssueOut[]): IssueOut[] {
	return [...issues].sort((a, b) => rank(a) - rank(b));
}
