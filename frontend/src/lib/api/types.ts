// Mirror of the backend models the UI consumes. The backend is the source of truth:
// src/la_rp_peace/enums.py and src/la_rp_peace/api/schemas.py.

/** Which part of the comparison a document belongs to. */
export type DocSet = 'before' | 'after' | 'regulatory' | 'benchmark';

/** Formats the backend can parse. */
export type DocFormat = 'docx' | 'pdf' | 'xlsx';

/**
 * Lifecycle of a document's parsing. `pending` lasts until the background parser finishes; a
 * failed parse ends in `needs_review` with a blocking issue, never stays `pending`.
 */
export type ParseStatus = 'pending' | 'parsed' | 'needs_review' | 'validated';

/** `DocumentOut`: a registered document with its metadata card and parsing status. */
export interface DocumentOut {
	id: number;
	file_name: string;
	set: DocSet | null;
	source_format: DocFormat;
	file_size_bytes: number;
	content_sha256: string;
	uploaded_at: string;
	parse_status: ParseStatus;
	title: string | null;
	/** Free text: read from the document by the parser, correctable by the user. */
	document_type: string | null;
	organization: string | null;
	revision: string | null;
	approved_by: string | null;
	approval_document_type: string | null;
	approval_number: string | null;
	document_created_on: string | null;
	approved_on: string | null;
	effective_from: string | null;
	node_count: number;
	/** Unresolved parsing issues that make the parse unusable until reviewed. */
	blocking_issues: number;
	other_issues: number;
}

/** Lifecycle of an analysis run, as planned in .agents/backend.md «Analyses and live progress». */
export type AnalysisStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

/**
 * An analysis run as `POST /api/analyses` answers it. Proposed contract (.agents/frontend.md §4):
 * the backend does not serve analyses yet.
 */
export interface AnalysisOut {
	id: number;
	name: string;
	status: AnalysisStatus;
}
