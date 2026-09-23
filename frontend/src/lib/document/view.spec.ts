import { afterEach, describe, expect, it, vi } from 'vitest';

import type { DocumentApi, DocumentOut, ParseStatus } from '$lib/api/document';
import { ApiError } from '$lib/api/errors';

import { DocumentView, POLL_INTERVAL_MS, parseDocumentId } from './view.svelte';

function stored(parseStatus: ParseStatus = 'parsed'): DocumentOut {
	return {
		id: 7,
		file_name: 'Положение_ред_9.docx',
		set: 'before',
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

const PROFILE = { parsing_profile: null, metadata_evidence: {}, file_metadata: {} };
const NODES = [
	{
		id: 1,
		parent_id: null,
		position: 0,
		node_type: 'clause' as const,
		marker: '1',
		text: '1. Общие положения',
		source_start: 0,
		source_end: 18,
		anchor: 'п. 1',
		path: 'п. 1',
		location: {}
	}
];

function fakeApi(overrides: Partial<DocumentApi> = {}): DocumentApi {
	return {
		get: vi.fn(async () => stored()),
		nodes: vi.fn(async () => NODES),
		issues: vi.fn(async () => []),
		profile: vi.fn(async () => PROFILE),
		...overrides
	};
}

afterEach(() => {
	vi.useRealTimers();
});

describe('parseDocumentId', () => {
	it('accepts positive integers only', () => {
		expect(parseDocumentId('7')).toBe(7);
		expect(parseDocumentId('120')).toBe(120);
		for (const param of ['0', '07', '-1', '1.5', 'abc', '', '1e3', '99999999999999999']) {
			expect(parseDocumentId(param)).toBeNull();
		}
	});
});

describe('DocumentView', () => {
	it('loads the card, the tree, the issues and the evidence', async () => {
		const api = fakeApi();
		const view = new DocumentView(api, 7);

		view.start();

		expect(view.status).toBe('loading');
		await vi.waitFor(() => expect(view.status).toBe('ready'));
		expect(view.document?.file_name).toBe('Положение_ред_9.docx');
		expect(view.details).toEqual({ nodes: NODES, issues: [], profile: PROFILE });
		expect(api.nodes).toHaveBeenCalledWith(7);
		expect(api.issues).toHaveBeenCalledWith(7);
		expect(api.profile).toHaveBeenCalledWith(7);
	});

	it('checks a pending document every 2 s until parsing is over', async () => {
		vi.useFakeTimers();
		const get = vi
			.fn<DocumentApi['get']>()
			.mockResolvedValueOnce(stored('pending'))
			.mockResolvedValueOnce(stored('pending'))
			.mockResolvedValueOnce(stored('needs_review'));
		const api = fakeApi({ get });
		const view = new DocumentView(api, 7);

		view.start();
		await vi.advanceTimersByTimeAsync(0);
		expect(view.status).toBe('pending');
		expect(view.document?.parse_status).toBe('pending');
		expect(api.nodes).not.toHaveBeenCalled();

		await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
		expect(get).toHaveBeenCalledTimes(2);
		expect(view.status).toBe('pending');

		await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
		expect(get).toHaveBeenCalledTimes(3);
		expect(view.status).toBe('ready');
		expect(view.document?.parse_status).toBe('needs_review');

		await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
		expect(get).toHaveBeenCalledTimes(3);
	});

	it('stops polling when stopped', async () => {
		vi.useFakeTimers();
		const get = vi.fn(async () => stored('pending'));
		const view = new DocumentView(fakeApi({ get }), 7);
		view.start();
		await vi.advanceTimersByTimeAsync(0);

		view.stop();
		await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);

		expect(get).toHaveBeenCalledTimes(1);
	});

	it('ignores an answer that arrives after stop', async () => {
		let answer: (document: DocumentOut) => void = () => {};
		const get = vi.fn(() => new Promise<DocumentOut>((resolve) => (answer = resolve)));
		const view = new DocumentView(fakeApi({ get }), 7);
		view.start();

		view.stop();
		answer(stored());
		await Promise.resolve();

		expect(view.document).toBeNull();
		expect(view.status).toBe('loading');
	});

	it('reports a missing document as not found', async () => {
		const api = fakeApi({
			get: vi.fn().mockRejectedValue(new ApiError('Документ не найден', 404))
		});
		const view = new DocumentView(api, 7);

		view.start();

		await vi.waitFor(() => expect(view.status).toBe('not_found'));
		expect(view.error).toBeNull();
	});

	it('does not ask the backend for an id that cannot exist', () => {
		const api = fakeApi();
		const view = new DocumentView(api, null);

		view.start();

		expect(view.status).toBe('not_found');
		expect(api.get).not.toHaveBeenCalled();
	});

	it('shows the backend message when a request fails, and retries on demand', async () => {
		const issues = vi
			.fn<DocumentApi['issues']>()
			.mockRejectedValueOnce(new ApiError('Сервер недоступен', 0))
			.mockResolvedValueOnce([]);
		const view = new DocumentView(fakeApi({ issues }), 7);
		view.start();
		await vi.waitFor(() => expect(view.status).toBe('failed'));
		expect(view.error).toBe('Сервер недоступен');
		expect(view.document).not.toBeNull();

		view.retry();

		expect(view.status).toBe('loading');
		expect(view.error).toBeNull();
		await vi.waitFor(() => expect(view.status).toBe('ready'));
	});
});
