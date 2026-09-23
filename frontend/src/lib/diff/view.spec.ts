import { afterEach, describe, expect, it, vi } from 'vitest';

import type { DocumentApi, DocumentOut, NodeOut, ParseStatus } from '$lib/api/document';
import { ApiError } from '$lib/api/errors';
import { POLL_INTERVAL_MS } from '$lib/document/view.svelte';

import { CompareView } from './view.svelte';

function stored(id: number, parseStatus: ParseStatus = 'parsed'): DocumentOut {
	return {
		id,
		file_name: `Положение_${id}.docx`,
		set: id === 7 ? 'before' : 'after',
		source_format: 'docx',
		file_size_bytes: 52_000,
		content_sha256: 'ab12',
		uploaded_at: '2026-09-23T10:00:00Z',
		parse_status: parseStatus,
		title: null,
		document_type: null,
		organization: null,
		revision: null,
		approved_by: null,
		approval_document_type: null,
		approval_number: null,
		document_created_on: null,
		approved_on: null,
		effective_from: null,
		node_count: 1,
		blocking_issues: 0,
		other_issues: 0
	};
}

function nodesOf(documentId: number): NodeOut[] {
	return [
		{
			id: documentId * 100,
			parent_id: null,
			position: 0,
			node_type: 'clause',
			marker: '1',
			text: '1. Общие положения',
			source_start: 0,
			source_end: 18,
			anchor: 'п. 1',
			path: 'п. 1',
			location: {}
		}
	];
}

function fakeApi(overrides: Partial<DocumentApi> = {}): DocumentApi {
	return {
		get: vi.fn(async (id: number) => stored(id)),
		nodes: vi.fn(async (id: number) => nodesOf(id)),
		issues: vi.fn(async () => []),
		profile: vi.fn(async () => ({
			parsing_profile: null,
			metadata_evidence: {},
			file_metadata: {}
		})),
		...overrides
	};
}

afterEach(() => {
	vi.useRealTimers();
});

describe('CompareView', () => {
	it('loads the cards and the nodes of both documents', async () => {
		const api = fakeApi();
		const view = new CompareView(api, 7, 9);

		view.start();
		expect(view.status).toBe('loading');
		await vi.waitFor(() => expect(view.status).toBe('ready'));

		expect(view.before?.document.id).toBe(7);
		expect(view.before?.nodes).toEqual(nodesOf(7));
		expect(view.after?.document.id).toBe(9);
		expect(view.after?.nodes).toEqual(nodesOf(9));
		expect(api.nodes).toHaveBeenCalledTimes(2);
	});

	it('asks for two documents when an id is missing and never calls the API', () => {
		const api = fakeApi();
		const view = new CompareView(api, 7, null);

		view.start();

		expect(view.status).toBe('missing');
		expect(api.get).not.toHaveBeenCalled();
	});

	it('refuses to compare a document with itself', () => {
		const api = fakeApi();
		const view = new CompareView(api, 7, 7);

		view.start();

		expect(view.status).toBe('same');
		expect(api.get).not.toHaveBeenCalled();
	});

	it('shows the backend message with the side that failed, and retries', async () => {
		const get = vi.fn(async (id: number) => {
			if (id === 9) {
				throw new ApiError('Документ не найден', 404);
			}
			return stored(id);
		});
		const api = fakeApi({ get });
		const view = new CompareView(api, 7, 9);

		view.start();
		await vi.waitFor(() => expect(view.status).toBe('failed'));
		expect(view.error).toBe('Документ «После»: Документ не найден');

		get.mockImplementation(async (id: number) => stored(id));
		view.retry();
		expect(view.status).toBe('loading');
		await vi.waitFor(() => expect(view.status).toBe('ready'));
		expect(view.error).toBeNull();
	});

	it('reports a failed node list the same way', async () => {
		const api = fakeApi({
			nodes: vi.fn(async () => {
				throw new ApiError('Сервер недоступен. Проверьте, что бэкенд запущен.', 0);
			})
		});
		const view = new CompareView(api, 7, 9);

		view.start();
		await vi.waitFor(() => expect(view.status).toBe('failed'));

		expect(view.error).toBe('Документ «До»: Сервер недоступен. Проверьте, что бэкенд запущен.');
	});

	it('waits while a document is still parsed, then loads', async () => {
		vi.useFakeTimers();
		const get = vi.fn(async (id: number) => stored(id, id === 9 ? 'pending' : 'parsed'));
		const api = fakeApi({ get });
		const view = new CompareView(api, 7, 9);

		view.start();
		await vi.waitFor(() => expect(view.status).toBe('pending'));
		expect(api.nodes).not.toHaveBeenCalled();

		get.mockImplementation(async (id: number) => stored(id));
		await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);

		await vi.waitFor(() => expect(view.status).toBe('ready'));
	});

	it('ignores answers after it was stopped', async () => {
		vi.useFakeTimers();
		const api = fakeApi({ get: vi.fn(async (id: number) => stored(id, 'pending')) });
		const view = new CompareView(api, 7, 9);

		view.start();
		await vi.waitFor(() => expect(view.status).toBe('pending'));
		view.stop();
		await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);

		expect(api.get).toHaveBeenCalledTimes(2);
	});
});
