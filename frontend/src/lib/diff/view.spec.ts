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

	it.each([
		[7, '«До»', 0],
		[9, '«После»', 0],
		[7, '«До»', 1],
		[9, '«После»', 1]
	])(
		'refuses a blocking parse issue in document %i (%s), with %i nodes',
		async (id, label, count) => {
			const api = fakeApi({
				get: vi.fn(async (documentId: number) =>
					documentId === id
						? { ...stored(id, 'needs_review'), blocking_issues: 1, node_count: count }
						: stored(documentId)
				)
			});
			const view = new CompareView(api, 7, 9);

			view.start();
			await vi.waitFor(() => expect(view.status).toBe('failed'));

			expect(view.error).toContain(`в документе ${label}`);
			expect(view.error).toContain('блокирующие проблемы разбора');
			expect(api.nodes).not.toHaveBeenCalled();
			expect(view.before).toBeNull();
			expect(view.after).toBeNull();
		}
	);

	it('reports both documents when both have blocking issues', async () => {
		const api = fakeApi({
			get: vi.fn(async (id: number) => ({
				...stored(id, 'needs_review'),
				blocking_issues: 1
			}))
		});
		const view = new CompareView(api, 7, 9);

		view.start();
		await vi.waitFor(() => expect(view.status).toBe('failed'));

		expect(view.error).toContain('в документах «До» и «После»');
		expect(api.nodes).not.toHaveBeenCalled();
	});

	it('allows review warnings when neither document has blocking issues', async () => {
		const api = fakeApi({
			get: vi.fn(async (id: number) => ({ ...stored(id, 'needs_review'), other_issues: 2 }))
		});
		const view = new CompareView(api, 7, 9);

		view.start();
		await vi.waitFor(() => expect(view.status).toBe('ready'));

		expect(api.nodes).toHaveBeenCalledTimes(2);
		expect(view.error).toBeNull();
	});

	it('can retry after blocking parsing issues are resolved', async () => {
		const get = vi.fn(async (id: number) => ({
			...stored(id, 'needs_review'),
			blocking_issues: 1
		}));
		const api = fakeApi({ get });
		const view = new CompareView(api, 7, 9);

		view.start();
		await vi.waitFor(() => expect(view.status).toBe('failed'));
		get.mockImplementation(async (id: number) => stored(id, 'validated'));
		view.retry();
		await vi.waitFor(() => expect(view.status).toBe('ready'));

		expect(view.error).toBeNull();
		expect(api.nodes).toHaveBeenCalledTimes(2);
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

	it('stops polling when parsing finishes with blocking issues', async () => {
		vi.useFakeTimers();
		const get = vi.fn(async (id: number) => stored(id, id === 9 ? 'pending' : 'parsed'));
		const api = fakeApi({ get });
		const view = new CompareView(api, 7, 9);

		view.start();
		await vi.waitFor(() => expect(view.status).toBe('pending'));
		get.mockImplementation(async (id: number) => ({
			...stored(id, id === 9 ? 'needs_review' : 'parsed'),
			blocking_issues: id === 9 ? 1 : 0
		}));
		await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
		await vi.waitFor(() => expect(view.status).toBe('failed'));
		await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);

		expect(api.get).toHaveBeenCalledTimes(4);
		expect(api.nodes).not.toHaveBeenCalled();
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
