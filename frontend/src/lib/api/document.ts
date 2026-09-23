// Mirror of the document page's backend models: src/la_rp_peace/api/schemas.py and
// src/la_rp_peace/enums.py on main. The backend is the source of truth.
import { env } from '$env/dynamic/public';

import { ApiError, NETWORK_ERROR_MESSAGE, errorMessage } from './errors';
import type { DocSet } from './types';

/** Base URL of the FastAPI backend; the same default as `client.ts`. */
const API_URL = (env.PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

/** `pending` until the background parser has written the card, tree and issues. */
export type ParseStatus = 'pending' | 'parsed' | 'needs_review' | 'validated';

export type NodeType =
	| 'section'
	| 'clause'
	| 'heading'
	| 'list'
	| 'list_item'
	| 'table'
	| 'table_row'
	| 'table_cell'
	| 'text'
	| 'service';

/** Card fields of a document; NULL unless the backend verified the value against the text. */
export interface DocumentCardValues {
	title: string | null;
	document_type: string | null;
	organization: string | null;
	revision: string | null;
	approved_by: string | null;
	approval_document_type: string | null;
	approval_number: string | null;
	document_created_on: string | null;
	approved_on: string | null;
	effective_from: string | null;
}

/** `GET /api/documents/{id}`: file facts, metadata card and parsing status. */
export interface DocumentOut extends DocumentCardValues {
	id: number;
	file_name: string;
	set: DocSet | null;
	source_format: string;
	file_size_bytes: number;
	content_sha256: string;
	uploaded_at: string;
	parse_status: ParseStatus;
	node_count: number;
	/** Unresolved issues only. */
	blocking_issues: number;
	other_issues: number;
}

/** One node of the document tree, with its human-readable place («п. 3.4 «а»»). */
export interface NodeOut {
	id: number;
	parent_id: number | null;
	position: number;
	node_type: NodeType;
	marker: string | null;
	text: string;
	source_start: number;
	source_end: number;
	anchor: string;
	path: string;
	/** `{"page": 6}` for PDF, `{"paragraph": 103}` for DOCX; empty when unknown. */
	location: Record<string, unknown>;
}

/** A parsing issue; `issue_type` is one of the backend's `IssueType` values. */
export interface IssueOut {
	id: number;
	node_id: number | null;
	issue_type: string;
	message: string;
	is_blocking: boolean;
	resolved_at: string | null;
	created_at: string;
}

/** What the agent decided about a document; `metadata_evidence` backs the card. */
export interface ProfileOut {
	parsing_profile: Record<string, unknown> | null;
	metadata_evidence: Record<string, unknown>;
	file_metadata: Record<string, unknown>;
}

/** Reads of one document; injected so the document page logic is testable. */
export interface DocumentApi {
	get(id: number): Promise<DocumentOut>;
	nodes(id: number): Promise<NodeOut[]>;
	issues(id: number): Promise<IssueOut[]>;
	profile(id: number): Promise<ProfileOut>;
}

async function getJson<T>(path: string): Promise<T> {
	let response: Response;
	try {
		response = await fetch(`${API_URL}${path}`);
	} catch {
		throw new ApiError(NETWORK_ERROR_MESSAGE, 0);
	}
	if (!response.ok) {
		const body: unknown = await response.json().catch(() => null);
		throw new ApiError(errorMessage(body, response.status), response.status);
	}
	return (await response.json()) as T;
}

/** URL that downloads the original file as uploaded. */
export function fileUrl(id: number): string {
	return `${API_URL}/api/documents/${id}/file`;
}

export const documentApi: DocumentApi = {
	get: (id) => getJson(`/api/documents/${id}`),
	nodes: (id) => getJson(`/api/documents/${id}/nodes`),
	issues: (id) => getJson(`/api/documents/${id}/issues`),
	profile: (id) => getJson(`/api/documents/${id}/profile`)
};
