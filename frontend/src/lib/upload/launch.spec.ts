import { describe, expect, it, vi } from 'vitest';

import type { AnalysesApi } from '$lib/api/client';
import { ApiError } from '$lib/api/errors';
import type { DocSet, DocumentOut } from '$lib/api/types';

import {
	AnalysisLauncher,
	analysisDocumentIds,
	analysisName,
	launchBlocker
} from './launch.svelte';
import { UploadItem, type UploadStatus } from './session.svelte';

function document(id: number, overrides: Partial<DocumentOut> = {}): DocumentOut {
	return {
		id,
		file_name: `doc-${id}.docx`,
		set: 'before',
		source_format: 'docx',
		file_size_bytes: 7,
		content_sha256: 'ab12',
		uploaded_at: '2026-09-23T10:00:00Z',
		parse_status: 'validated',
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
		node_count: 42,
		blocking_issues: 0,
		other_issues: 0,
		...overrides
	};
}

/** A file in the given state; a stored document is attached from `parsing` on. */
function item(
	set: DocSet,
	status: UploadStatus,
	id: number,
	overrides: Partial<DocumentOut> = {}
): UploadItem {
	const upload = new UploadItem(new File(['content'], `${set}-${id}.docx`), set);
	upload.status = status;
	if (status !== 'uploading' && status !== 'failed') {
		upload.document = document(id, { set, ...overrides });
	}
	return upload;
}

const ready = () => [item('before', 'parsed', 1), item('after', 'parsed', 2)];

describe('launchBlocker', () => {
	it('asks for the required documents that are missing', () => {
		expect(launchBlocker([])).toBe('Загрузите документы «До» и «После».');
		expect(launchBlocker([item('before', 'parsed', 1)])).toBe('Загрузите документ «После».');
		expect(launchBlocker([item('regulatory', 'parsed', 3)])).toBe(
			'Загрузите документы «До» и «После».'
		);
	});

	it('waits while any file is uploading or parsing', () => {
		expect(launchBlocker([...ready(), item('benchmark', 'parsing', 3)])).toBe(
			'Дождитесь окончания разбора.'
		);
		expect(launchBlocker([item('before', 'uploading', 1), item('after', 'parsed', 2)])).toBe(
			'Дождитесь окончания разбора.'
		);
	});

	it('names a file that failed', () => {
		expect(launchBlocker([item('before', 'failed', 1), item('after', 'parsed', 2)])).toBe(
			'Файл «before-1.docx» не загружен: повторите загрузку или удалите его.'
		);
	});

	it('names a file whose parse has blocking issues', () => {
		const review = item('after', 'needs_review', 2, {
			parse_status: 'needs_review',
			blocking_issues: 1
		});
		expect(launchBlocker([item('before', 'parsed', 1), review])).toBe(
			'В файле «after-2.docx» есть блокирующие проблемы разбора: удалите его или загрузите другой.'
		);
	});

	it('lets a review with only minor issues through', () => {
		const review = item('after', 'needs_review', 2, {
			parse_status: 'needs_review',
			other_issues: 4
		});
		expect(launchBlocker([item('before', 'parsed', 1), review])).toBeNull();
	});
});

describe('analysisDocumentIds', () => {
	it('takes every parsed document of every set in upload order', () => {
		const items = [item('regulatory', 'parsed', 5), item('benchmark', 'failed', 6), ...ready()];
		expect(analysisDocumentIds(items)).toEqual([5, 1, 2]);
	});
});

describe('analysisName', () => {
	it('stamps the local date and time', () => {
		expect(analysisName(new Date(2026, 8, 23, 16, 5))).toBe('Анализ от 23.09.2026, 16:05');
	});
});

describe('AnalysisLauncher.start', () => {
	const now = new Date(2026, 8, 23, 16, 5);

	it('starts the analysis on the parsed documents and returns its id', async () => {
		const api: AnalysesApi = {
			start: vi.fn(async (name: string) => ({ id: 11, name, status: 'queued' as const }))
		};
		const launcher = new AnalysisLauncher(api);

		const id = await launcher.start(ready(), now);

		expect(id).toBe(11);
		expect(api.start).toHaveBeenCalledWith('Анализ от 23.09.2026, 16:05', [1, 2]);
		expect(launcher.starting).toBe(true);
		expect(launcher.error).toBeNull();
	});

	it('does not call the backend while something blocks the start', async () => {
		const api: AnalysesApi = { start: vi.fn() };
		const launcher = new AnalysisLauncher(api);

		const id = await launcher.start([item('before', 'parsed', 1)], now);

		expect(id).toBeNull();
		expect(api.start).not.toHaveBeenCalled();
	});

	it('shows the backend message and allows another try when the start fails', async () => {
		const api: AnalysesApi = {
			start: vi.fn().mockRejectedValue(new ApiError('Сервер недоступен', 0))
		};
		const launcher = new AnalysisLauncher(api);

		const id = await launcher.start(ready(), now);

		expect(id).toBeNull();
		expect(launcher.error).toBe('Сервер недоступен');
		expect(launcher.starting).toBe(false);
	});
});
