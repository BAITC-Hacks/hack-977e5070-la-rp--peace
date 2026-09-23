// Result of an analysis job, as in docs/spec/tz_site.md §5 (result.json). One deviation: a source
// cites a backend node (`node_id`) instead of `clause_id`, per the traceability contract in
// .agents/backend.md. Optional fields may be absent or null.

/** Which version of the document a clause belongs to. */
export type DocSide = 'before' | 'after';

/** Kind of change or problem a finding reports; each kind has its own colour (colors.css). */
export type FindingType =
	| 'kept'
	| 'transformed'
	| 'created'
	| 'abolished'
	| 'moved'
	| 'loss'
	| 'duplication'
	| 'conflict'
	| 'contradiction'
	| 'overlap';

/** Badge on a unit or function in the «до» / «после» columns (tech task §6.3). */
export type ItemStatus = 'kept' | 'transformed' | 'created' | 'abolished' | 'moved' | 'loss';

export type Confidence = 'high' | 'medium' | 'low';

/** The responsible employee's check of a finding: confirmed or rejected. */
export type Verdict = 'ok' | 'no';

/** A verbatim quote from one node of an uploaded document. */
export interface Source {
	doc: DocSide;
	/** Block of the document the node belongs to, e.g. «Положение ДИБиР». */
	block: string;
	/** Node of the parsed document (`GET /api/nodes/{node_id}`). */
	node_id: number;
	/** Clause number as printed in the document, e.g. «п. 2.8». */
	clause: string;
	quote: string;
	/** Block item the quote belongs to, if it is shown in the columns. */
	item: string | null;
}

/** `fact` rests on quotes; `inference` is the agent's reasoning and is labelled as such (I3). */
export type StepKind = 'fact' | 'inference';

export interface Step {
	kind: StepKind;
	text: string;
	sources: Source[];
}

/** A near match that stayed below the threshold. */
export interface Candidate {
	label: string;
	clause: string;
	/** Similarity, 0..1. */
	score: number;
	item: string | null;
}

/** What was searched before concluding that something is absent (I4). */
export interface Checked {
	scope: string;
	threshold: number;
	candidates: Candidate[];
}

export interface Evidence {
	conclusion: string;
	/** How the conclusion was reached. */
	method: string;
	steps: Step[];
	/** Required for `loss` and `created`. */
	checked?: Checked | null;
	/** Regulatory basis, or why there is none. */
	npa?: string | null;
	confidence: Confidence;
	confidence_note?: string | null;
}

/** One card in the middle column of the visual comparison. */
export interface Finding {
	id: string;
	type: FindingType;
	block: string;
	title: string;
	desc?: string | null;
	/** Items of the «до» column the finding starts from. */
	from: string[];
	/** Items of the «после» column the finding leads to. */
	to: string[];
	/** Further «после» items involved; drawn dashed. */
	also?: string[] | null;
	evidence: Evidence;
	review: Verdict | null;
}

/** A unit or function shown in the «до» or «после» column. */
export interface BlockItem {
	id: string;
	label: string;
	status?: ItemStatus | null;
	clause_id: string;
}

export interface Block {
	title: string;
	before: BlockItem[];
	after: BlockItem[];
	/** Ids of the block's findings, in display order. */
	changes: string[];
}

export interface JobSummary {
	changed_blocks: string[];
	counts: Partial<Record<FindingType, number>>;
}

export interface JobResult {
	job_id: string;
	summary: JobSummary;
	/** Short conclusion; mentions findings by id, e.g. «C-011». */
	conclusion: string;
	blocks: Block[];
	findings: Record<string, Finding>;
}
