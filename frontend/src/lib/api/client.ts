import { env } from '$env/dynamic/public';

import { ApiError, NETWORK_ERROR_MESSAGE, errorMessage } from './errors';
import type { DocSet, DocumentOut } from './types';

/** Base URL of the FastAPI backend; the default matches its local `uvicorn` run and CORS config. */
export const API_URL = (env.PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

/** `fetch` of an API path; any failure becomes an `ApiError` carrying the backend's message. */
export async function request(path: string, init: RequestInit = {}): Promise<Response> {
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

/** Document operations the upload screen needs; injected so the upload logic is testable. */
export interface DocumentsApi {
	/** Resolves once the backend has stored the file and queued it for parsing (HTTP 202). */
	upload(file: File, set: DocSet, onProgress: (fraction: number) => void): Promise<DocumentOut>;
	get(id: number): Promise<DocumentOut>;
	setType(id: number, documentType: string): Promise<DocumentOut>;
	remove(id: number): Promise<void>;
}

/** `POST /api/documents` via XHR, because `fetch` cannot report upload progress. */
function upload(
	file: File,
	set: DocSet,
	onProgress: (fraction: number) => void
): Promise<DocumentOut> {
	return new Promise((resolve, reject) => {
		const xhr = new XMLHttpRequest();
		xhr.open('POST', `${API_URL}/api/documents`);
		xhr.responseType = 'json';
		xhr.upload.onprogress = (event) => {
			if (event.lengthComputable) {
				onProgress(event.loaded / event.total);
			}
		};
		xhr.onload = () => {
			if (xhr.status >= 200 && xhr.status < 300) {
				resolve(xhr.response as DocumentOut);
			} else {
				reject(new ApiError(errorMessage(xhr.response, xhr.status), xhr.status));
			}
		};
		xhr.onerror = () => reject(new ApiError(NETWORK_ERROR_MESSAGE, 0));
		const body = new FormData();
		body.append('set', set);
		body.append('file', file);
		xhr.send(body);
	});
}

async function get(id: number): Promise<DocumentOut> {
	const response = await request(`/api/documents/${id}`);
	return (await response.json()) as DocumentOut;
}

async function setType(id: number, documentType: string): Promise<DocumentOut> {
	const response = await request(`/api/documents/${id}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ document_type: documentType })
	});
	return (await response.json()) as DocumentOut;
}

async function remove(id: number): Promise<void> {
	await request(`/api/documents/${id}`, { method: 'DELETE' });
}

export const documentsApi: DocumentsApi = { upload, get, setType, remove };
