import { env } from '$env/dynamic/public';

import { ApiError, NETWORK_ERROR_MESSAGE, errorMessage } from './errors';
import type { ApiDocument, DocSet, DocType } from './types';

/** Base URL of the FastAPI backend; the default matches its local `uvicorn` run and CORS config. */
const API_URL = (env.PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

/** Document operations the upload screen needs; injected so the upload logic is testable. */
export interface DocumentsApi {
	upload(file: File, set: DocSet, onProgress: (fraction: number) => void): Promise<ApiDocument>;
	setType(id: string, docType: DocType): Promise<ApiDocument>;
	remove(id: string): Promise<void>;
}

async function request(path: string, init: RequestInit): Promise<Response> {
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

/** `POST /api/documents` via XHR, because `fetch` cannot report upload progress. */
function upload(
	file: File,
	set: DocSet,
	onProgress: (fraction: number) => void
): Promise<ApiDocument> {
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
				resolve(xhr.response as ApiDocument);
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

async function setType(id: string, docType: DocType): Promise<ApiDocument> {
	const response = await request(`/api/documents/${encodeURIComponent(id)}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ doc_type: docType })
	});
	return (await response.json()) as ApiDocument;
}

async function remove(id: string): Promise<void> {
	await request(`/api/documents/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export const documentsApi: DocumentsApi = { upload, setType, remove };
