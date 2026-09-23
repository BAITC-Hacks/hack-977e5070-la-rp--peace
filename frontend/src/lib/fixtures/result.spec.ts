import { describe, expect, it } from 'vitest';

import result from './result.json';

// Local shape of result.json (tech task §5.3, sources cite `node_id`); plain strings so the
// JSON module is assignable without a cast. Enum values are checked by the tests below.
interface Source {
	doc: string;
	block: string;
	node_id: number;
	clause: string;
	quote: string;
	item: string | null;
}

interface Step {
	kind: string;
	text: string;
	sources: Source[];
}

interface Checked {
	scope: string;
	threshold: number;
	candidates: { label: string; clause: string; score: number; item: string | null }[];
}

interface Finding {
	id: string;
	type: string;
	block: string;
	title: string;
	desc: string | null;
	from: string[];
	to: string[];
	also: string[] | null;
	evidence: {
		conclusion: string;
		method: string;
		steps: Step[];
		checked: Checked | null;
		npa: string | null;
		confidence: string;
		confidence_note: string | null;
	};
	review: string | null;
}

interface BlockItem {
	id: string;
	label: string;
	status: string | null;
	clause_id: string;
}

interface Block {
	title: string;
	before: BlockItem[];
	after: BlockItem[];
	changes: string[];
}

interface Fixture {
	job_id: string;
	summary: { changed_blocks: string[]; counts: Record<string, number> };
	conclusion: string;
	blocks: Block[];
	findings: Record<string, Finding>;
}

const fixture: Fixture = result;

const FINDING_TYPES = [
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
const ITEM_STATUSES = ['kept', 'transformed', 'created', 'abolished', 'moved', 'loss'];
const CONFIDENCES = ['high', 'medium', 'low'];
const VERDICTS = ['ok', 'no'];
/** Findings that report a problem; the conclusion has to name each of them. */
const PROBLEM_TYPES = ['loss', 'duplication', 'conflict', 'contradiction', 'overlap'];

const findings = Object.values(fixture.findings);
const sourcesOf = (finding: Finding): Source[] =>
	finding.evidence.steps.flatMap((step) => step.sources);
const allSources = findings.flatMap(sourcesOf);
const items = fixture.blocks.flatMap((block) => [
	...block.before.map((item) => ({ item, side: 'before' })),
	...block.after.map((item) => ({ item, side: 'after' }))
]);
const itemSide = new Map(items.map(({ item, side }) => [item.id, side]));
const blockOf = (finding: Finding): Block => {
	const block = fixture.blocks.find((candidate) => candidate.title === finding.block);
	if (!block) throw new Error(`${finding.id}: no block «${finding.block}»`);
	return block;
};

describe('result.json findings', () => {
	it('are keyed by their id and use known types, confidence and verdicts', () => {
		expect(findings.length).toBeGreaterThan(0);
		for (const [id, finding] of Object.entries(fixture.findings)) {
			expect(finding.id).toBe(id);
			expect(id).toMatch(/^C-\d{3}$/);
			expect(FINDING_TYPES).toContain(finding.type);
			expect(CONFIDENCES).toContain(finding.evidence.confidence);
			expect(finding.review === null || VERDICTS.includes(finding.review)).toBe(true);
			expect(finding.title.trim()).not.toBe('');
			expect(finding.evidence.conclusion.trim()).not.toBe('');
			expect(finding.evidence.method.trim()).not.toBe('');
		}
	});

	it('each have at least one source with a quote (I1)', () => {
		for (const finding of findings) {
			expect(
				sourcesOf(finding).some((source) => source.quote.trim() !== ''),
				finding.id
			).toBe(true);
		}
	});

	it('quote verbatim fragments without ellipses or framing quotes (I2)', () => {
		for (const source of allSources) {
			expect(source.quote.trim()).not.toBe('');
			expect(source.quote).toBe(source.quote.trim());
			expect(source.quote).not.toMatch(/…|\.\.\./);
			expect(source.quote).not.toMatch(/^[«"“„']|[»"”']$/);
		}
	});

	it('separate facts with sources from inferences without them (I3)', () => {
		for (const finding of findings) {
			for (const step of finding.evidence.steps) {
				expect(['fact', 'inference'], finding.id).toContain(step.kind);
				expect(step.text.trim()).not.toBe('');
				if (step.kind === 'fact') {
					expect(step.sources.length, `${finding.id}: ${step.text}`).toBeGreaterThan(0);
				} else {
					expect(step.sources, `${finding.id}: ${step.text}`).toEqual([]);
				}
			}
		}
	});

	it('store what was checked for losses and created items (I4)', () => {
		const needChecked = findings.filter((f) => f.type === 'loss' || f.type === 'created');
		expect(needChecked.length).toBeGreaterThan(0);
		for (const finding of needChecked) {
			const checked = finding.evidence.checked;
			expect(checked, finding.id).not.toBeNull();
			if (!checked) continue;
			expect(checked.scope.trim()).not.toBe('');
			expect(checked.threshold).toBeGreaterThan(0);
			expect(checked.threshold).toBeLessThanOrEqual(1);
			expect(checked.candidates.length, finding.id).toBeGreaterThan(0);
			for (const candidate of checked.candidates) {
				expect(candidate.label.trim()).not.toBe('');
				expect(candidate.clause.trim()).not.toBe('');
				expect(candidate.score).toBeGreaterThanOrEqual(0);
				expect(candidate.score).toBeLessThan(checked.threshold);
				if (candidate.item !== null) expect(itemSide.has(candidate.item)).toBe(true);
			}
		}
	});
});

describe('result.json blocks', () => {
	it('list every finding exactly once, in the block the finding names', () => {
		const listed = fixture.blocks.flatMap((block) => block.changes);
		expect(new Set(listed).size).toBe(listed.length);
		expect([...listed].sort()).toEqual(Object.keys(fixture.findings).sort());
		for (const block of fixture.blocks) {
			for (const id of block.changes) expect(fixture.findings[id].block).toBe(block.title);
		}
	});

	it('link findings to items of their own block: from → «до», to and also → «после»', () => {
		for (const finding of findings) {
			const block = blockOf(finding);
			const before = block.before.map((item) => item.id);
			const after = block.after.map((item) => item.id);
			for (const id of finding.from) expect(before, finding.id).toContain(id);
			for (const id of [...finding.to, ...(finding.also ?? [])]) {
				expect(after, finding.id).toContain(id);
			}
		}
	});

	it('have unique item ids, known statuses and clause ids of their own side', () => {
		expect(itemSide.size).toBe(items.length);
		for (const { item, side } of items) {
			expect(item.label.trim()).not.toBe('');
			expect(item.status === null || ITEM_STATUSES.includes(item.status), item.id).toBe(true);
			expect(item.clause_id, item.id).toMatch(/^(before|after):[a-z0-9-]+:[a-z0-9._-]+$/);
			expect(item.clause_id.startsWith(`${side}:`), item.id).toBe(true);
		}
	});
});

describe('result.json sources', () => {
	it('come from «до» or «после» and point at existing items of the same side', () => {
		for (const source of allSources) {
			expect(['before', 'after']).toContain(source.doc);
			expect(source.block.trim()).not.toBe('');
			expect(source.clause.trim()).not.toBe('');
			if (source.item !== null) expect(itemSide.get(source.item), source.item).toBe(source.doc);
		}
	});

	it('give one node_id per clause (doc, block, clause) and different ids to different clauses', () => {
		const idOf = new Map<string, number>();
		const clauseOf = new Map<number, string>();
		for (const source of allSources) {
			expect(Number.isInteger(source.node_id)).toBe(true);
			expect(source.node_id).toBeGreaterThan(0);
			const clause = `${source.doc} | ${source.block} | ${source.clause}`;
			expect(idOf.get(clause) ?? source.node_id, clause).toBe(source.node_id);
			expect(clauseOf.get(source.node_id) ?? clause, String(source.node_id)).toBe(clause);
			idOf.set(clause, source.node_id);
			clauseOf.set(source.node_id, clause);
		}
	});

	it('quote each item from a single clause', () => {
		const clauseOfItem = new Map<string, number>();
		for (const source of allSources) {
			if (source.item === null) continue;
			expect(clauseOfItem.get(source.item) ?? source.node_id, source.item).toBe(source.node_id);
			clauseOfItem.set(source.item, source.node_id);
		}
	});
});

describe('result.json summary and conclusion', () => {
	it('count findings by type without zeros', () => {
		const counts: Record<string, number> = {};
		for (const finding of findings) counts[finding.type] = (counts[finding.type] ?? 0) + 1;
		expect(fixture.summary.counts).toEqual(counts);
		expect(Object.values(fixture.summary.counts)).not.toContain(0);
	});

	it('list the blocks that have findings other than «kept»', () => {
		const changed = fixture.blocks
			.filter((block) => block.changes.some((id) => fixture.findings[id].type !== 'kept'))
			.map((block) => block.title);
		expect(fixture.summary.changed_blocks).toEqual(changed);
	});

	it('has 3–6 sentences, each citing existing findings (P0.9)', () => {
		const sentences = fixture.conclusion.trim().split(/(?<=[.!?])\s+/);
		expect(sentences.length).toBeGreaterThanOrEqual(3);
		expect(sentences.length).toBeLessThanOrEqual(6);
		for (const sentence of sentences) {
			const cited = sentence.match(/C-\d+/g) ?? [];
			expect(cited.length, sentence).toBeGreaterThan(0);
			for (const id of cited) expect(Object.keys(fixture.findings), sentence).toContain(id);
		}
	});

	it('names every problem finding', () => {
		for (const finding of findings.filter((f) => PROBLEM_TYPES.includes(f.type))) {
			expect(fixture.conclusion).toContain(finding.id);
		}
	});
});
