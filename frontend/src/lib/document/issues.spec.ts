import { describe, expect, it } from 'vitest';

import type { IssueOut } from '$lib/api/document';

import { sortIssues } from './issues';
import { issueTypeLabel } from './labels';

function issue(id: number, isBlocking: boolean, resolvedAt: string | null = null): IssueOut {
	return {
		id,
		node_id: null,
		issue_type: 'numbering_gap',
		message: `Проблема ${id}`,
		is_blocking: isBlocking,
		resolved_at: resolvedAt,
		created_at: '2026-09-23T10:00:00Z'
	};
}

describe('sortIssues', () => {
	it('puts open blocking issues first and resolved ones last, keeping backend order', () => {
		const issues = [
			issue(1, false),
			issue(2, true, '2026-09-23T11:00:00Z'),
			issue(3, true),
			issue(4, false),
			issue(5, true)
		];

		expect(sortIssues(issues).map((item) => item.id)).toEqual([3, 5, 1, 4, 2]);
		expect(issues.map((item) => item.id)).toEqual([1, 2, 3, 4, 5]);
	});
});

describe('issueTypeLabel', () => {
	it('names known issue types and shows unknown ones as they are', () => {
		expect(issueTypeLabel('numbering_gap')).toBe('Пропуск в нумерации');
		expect(issueTypeLabel('new_kind')).toBe('new_kind');
		expect(issueTypeLabel('toString')).toBe('toString');
	});
});
