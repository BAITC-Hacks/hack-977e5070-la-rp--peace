import { FINDING_TYPES } from './labels';
import type { Block, Finding, FindingType, JobResult, Source } from './types';

/** Every source the finding's evidence quotes, in step order. */
export function findingSources(finding: Finding): Source[] {
	return finding.evidence.steps.flatMap((step) => step.sources);
}

/** I1: a finding without at least one quoted source is not shown. */
export function isSourced(finding: Finding): boolean {
	return findingSources(finding).some((source) => source.quote.trim() !== '');
}

/** All findings of the result that may be shown (I1). */
export function visibleFindings(result: JobResult): Finding[] {
	return Object.values(result.findings).filter(isSourced);
}

/** The block's findings that may be shown, in display order; unknown ids are skipped. */
export function blockFindings(block: Block, findings: Record<string, Finding>): Finding[] {
	return block.changes
		.map((id) => findings[id])
		.filter((finding): finding is Finding => finding !== undefined && isSourced(finding));
}

export interface TypeCount {
	type: FindingType;
	count: number;
}

/** Number of findings per type in the order of `FINDING_TYPES`, without zero counts. */
export function countByType(findings: Iterable<Finding>): TypeCount[] {
	const counts = new Map<FindingType, number>();
	for (const finding of findings) {
		counts.set(finding.type, (counts.get(finding.type) ?? 0) + 1);
	}
	return FINDING_TYPES.filter((type) => counts.has(type)).map((type) => ({
		type,
		count: counts.get(type) ?? 0
	}));
}

/** Column items the finding connects: `from`, `to` and `also`. */
export function linkedItems(finding: Finding): string[] {
	return [...finding.from, ...finding.to, ...(finding.also ?? [])];
}

/** Ids of the findings that connect the item. */
export function findingsOfItem(findings: readonly Finding[], itemId: string): string[] {
	return findings
		.filter((finding) => linkedItems(finding).includes(itemId))
		.map((finding) => finding.id);
}

/** What stays lit while some findings are hovered or focused; everything else is dimmed. */
export interface Focus {
	findings: Set<string>;
	items: Set<string>;
}

export function focusOf(findings: readonly Finding[], ids: readonly string[]): Focus {
	const focused = findings.filter((finding) => ids.includes(finding.id));
	return {
		findings: new Set(focused.map((finding) => finding.id)),
		items: new Set(focused.flatMap(linkedItems))
	};
}

export type ConclusionPart = { kind: 'text'; text: string } | { kind: 'finding'; id: string };

const FINDING_ID = /C-\d+/g;

/** Splits the conclusion so that mentions of shown findings («C-011») can become links. */
export function splitConclusion(text: string, shown: ReadonlySet<string>): ConclusionPart[] {
	const parts: ConclusionPart[] = [];
	let rest = 0;
	for (const match of text.matchAll(FINDING_ID)) {
		const id = match[0];
		if (!shown.has(id)) {
			continue;
		}
		if (match.index > rest) {
			parts.push({ kind: 'text', text: text.slice(rest, match.index) });
		}
		parts.push({ kind: 'finding', id });
		rest = match.index + id.length;
	}
	if (rest < text.length) {
		parts.push({ kind: 'text', text: text.slice(rest) });
	}
	return parts;
}
