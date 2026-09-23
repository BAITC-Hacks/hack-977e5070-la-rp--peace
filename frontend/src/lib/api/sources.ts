// Mirror of the backend source lookup: src/la_rp_peace/sources.py (SourceRef) and
// src/la_rp_peace/api/sources.py. The backend is the source of truth.
import { env } from '$env/dynamic/public';

import { ApiError, NETWORK_ERROR_MESSAGE, errorMessage } from './errors';
import type { DocSet } from './types';

/** Base URL of the FastAPI backend; the same default as `client.ts`. */
const API_URL = (env.PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

/**
 * Position in the original file, as the parser recorded it: `{page}` for PDF, `{paragraph}`
 * (0-based body item index) for DOCX, `{sheet, row}` for XLSX; may be empty or carry extra keys.
 */
export type SourceLocation = Record<string, unknown>;

/** A verified citation: the exact words of an original document and where to find them. */
export interface SourceRef {
	node_id: number;
	document_id: number;
	document_name: string;
	set: DocSet | null;
	/** Short citation, e.g. «п. 3.4 «а»». */
	anchor: string;
	/** Where to look, from the section down, e.g. «Разд. 3 «…» › п. 3.4 › подп. «а»». */
	path: string;
	location: SourceLocation;
	/** The cited words, as they appear in the document. */
	quote: string;
	/** The node's own text containing the quote. */
	context: string;
	/** Offset of the quote in `context`, in code points. */
	start: number;
	/** Offset just past the quote in `context`, in code points. */
	end: number;
}

/**
 * Source lookups the source panel needs; injected so the panel and its components are testable
 * without the backend (and without `$env`, which only the SvelteKit runtime provides).
 */
export interface SourcesApi {
	/** A node as a source quoting its whole own text. */
	getNodeSource(nodeId: number): Promise<SourceRef>;
	/** Verifies that `quote` occurs in the node; rejects with status 422 when it does not. */
	resolveSource(nodeId: number, quote: string): Promise<SourceRef>;
	/** Download link of the original uploaded file. */
	fileUrl(documentId: number): string;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
	let response: Response;
	try {
		response = await fetch(`${API_URL}${path}`, init);
	} catch {
		throw new ApiError(NETWORK_ERROR_MESSAGE, 0);
	}
	if (!response.ok) {
		const body: unknown = await response.json().catch(() => null);
		throw new ApiError(errorMessage(body, response.status), response.status);
	}
	return response;
}

async function getNodeSource(nodeId: number): Promise<SourceRef> {
	const response = await request(`/api/nodes/${encodeURIComponent(nodeId)}`);
	return (await response.json()) as SourceRef;
}

async function resolveSource(nodeId: number, quote: string): Promise<SourceRef> {
	const response = await request('/api/sources/resolve', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ node_id: nodeId, quote })
	});
	return (await response.json()) as SourceRef;
}

/** `GET /api/documents/{id}/file`: the backend sends it as an attachment. */
function fileUrl(documentId: number): string {
	return `${API_URL}/api/documents/${encodeURIComponent(documentId)}/file`;
}

export const sourcesApi: SourcesApi = { getNodeSource, resolveSource, fileUrl };
