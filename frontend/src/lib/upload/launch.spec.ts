import { describe, expect, it } from 'vitest';

import type { DocSet, DocumentOut } from '$lib/api/types';

import { launchBlocker } from './launch';
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

	it('lets files still uploading or parsing through, as the status screen follows them', () => {
		expect(launchBlocker([...ready(), item('benchmark', 'parsing', 3)])).toBeNull();
		expect(launchBlocker([item('before', 'uploading', 1), item('after', 'parsing', 2)])).toBeNull();
	});

	it('names a file that failed', () => {
		expect(launchBlocker([item('before', 'failed', 1), item('after', 'parsed', 2)])).toBe(
			'Файл «before-1.docx» не загружен: повторите загрузку или удалите его.'
		);
	});

	it('asks to retry the status request for a registered file after reload', () => {
		const restored = new UploadItem({ name: 'До.docx', size: 7 }, 'before');
		restored.documentId = 1;
		restored.status = 'failed';
		expect(launchBlocker([restored, item('after', 'parsed', 2)])).toBe(
			'Не удалось получить статус файла «До.docx»: повторите запрос или удалите его.'
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
