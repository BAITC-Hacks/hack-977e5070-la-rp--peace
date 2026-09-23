// Mirror of the backend models the UI consumes. The backend is the source of truth:
// src/la_rp_peace/enums.py and src/la_rp_peace/api/schemas.py (contract: .agents/frontend.md §4).

/** Which part of the comparison a document belongs to. */
export type DocSet = 'before' | 'after' | 'regulatory' | 'benchmark';

/** Kind of organisational document; detected by the backend, overridable by the user. */
export type DocType =
	| 'org_structure'
	| 'unit_regulation'
	| 'job_description'
	| 'order'
	| 'internal_regulation'
	| 'unknown';

/** Formats the backend can parse. */
export type DocFormat = 'docx' | 'pdf' | 'xlsx';

/** An uploaded document, as returned by `POST /api/documents` and `PATCH /api/documents/{id}`. */
export interface ApiDocument {
	id: string;
	filename: string;
	set: DocSet;
	doc_type: DocType;
	format: DocFormat;
	title: string | null;
	size: number;
	clause_count: number;
	created_at: string;
}
