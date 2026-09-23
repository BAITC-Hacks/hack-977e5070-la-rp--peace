import { describe, expect, it } from 'vitest';

import type { DocumentOut } from '$lib/api/types';
import type { UploadStatus } from '$lib/upload/session.svelte';

import { progressOf, type UploadProgress } from './from-upload';
import { errorMessage, overallStatus } from './stages';

function stored(overrides: Partial<DocumentOut> = {}): DocumentOut {
	return {
		id: 1,
		file_name: 'Положение_2024.docx',
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

function upload(
	status: UploadStatus,
	document: DocumentOut | null = null,
	error: string | null = null
): UploadProgress {
	return { set: 'before', file: new File([], 'Положение_2024.docx'), status, document, error };
}

describe('progressOf', () => {
	it('labels the row with the side and the file name', () => {
		expect(progressOf(upload('uploading')).label).toBe('До: Положение_2024.docx');
		expect(progressOf({ ...upload('uploading'), set: 'after' }).label).toBe(
			'После: Положение_2024.docx'
		);
	});

	it('runs the upload, then the parse', () => {
		expect(progressOf(upload('uploading')).stages).toEqual({
			uploaded: 'running',
			parsed: 'waiting',
			segmented: 'waiting'
		});
		expect(progressOf(upload('parsing', stored({ parse_status: 'pending' }))).stages).toEqual({
			uploaded: 'done',
			parsed: 'running',
			segmented: 'waiting'
		});
	});

	it('marks every stage done once the parse has ended without blocking issues', () => {
		for (const status of ['parsed', 'needs_review'] as const) {
			const row = progressOf(upload(status, stored({ other_issues: 3 })));
			expect(Object.values(row.stages)).toEqual(['done', 'done', 'done']);
			expect(overallStatus([row])).toBe('done');
		}
	});

	it('fails the segmentation when the parse has blocking issues', () => {
		const row = progressOf(
			upload('needs_review', stored({ parse_status: 'needs_review', blocking_issues: 2 }))
		);
		expect(row.stages.segmented).toBe('failed');
		expect(errorMessage(row)).toBe('Этап «Разбит на блоки»: блокирующих проблем разбора: 2');
	});

	it('fails the upload or the parse, whichever the file got stuck at, with the backend message', () => {
		const refused = progressOf(upload('failed', null, 'Файл больше 20 МБ'));
		expect(refused.stages.uploaded).toBe('failed');
		expect(errorMessage(refused)).toBe('Этап «Загружен»: Файл больше 20 МБ');

		const lost = progressOf(
			upload('failed', stored({ parse_status: 'pending' }), 'Сервер недоступен.')
		);
		expect(lost.stages).toMatchObject({ uploaded: 'done', parsed: 'failed' });
		expect(errorMessage(lost)).toBe('Этап «Распознан»: Сервер недоступен.');
	});
});
