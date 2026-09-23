import { describe, expect, it, vi } from 'vitest';

import type { DocumentsApi } from '$lib/api/client';
import { ApiError } from '$lib/api/errors';
import type { ApiDocument, DocSet, DocType } from '$lib/api/types';

import { UploadSession } from './session.svelte';

function storedDocument(
	file: File,
	set: DocSet,
	overrides: Partial<ApiDocument> = {}
): ApiDocument {
	return {
		id: `id-${file.name}`,
		filename: file.name,
		set,
		doc_type: 'unit_regulation',
		format: 'docx',
		title: null,
		size: file.size,
		clause_count: 42,
		created_at: '2026-09-23T10:00:00Z',
		...overrides
	};
}

/** A backend double whose upload resolves as soon as the progress callback reports every byte sent. */
function fakeApi(overrides: Partial<DocumentsApi> = {}): DocumentsApi {
	return {
		upload: vi.fn(async (file: File, set: DocSet, onProgress: (fraction: number) => void) => {
			onProgress(0.5);
			onProgress(1);
			return storedDocument(file, set);
		}),
		setType: vi.fn(async (id: string, docType: DocType) =>
			storedDocument(new File([], 'x.docx'), 'before', { id, doc_type: docType })
		),
		remove: vi.fn(async () => undefined),
		...overrides
	};
}

const docx = (name = 'Положение_ред_9.docx') => new File(['content'], name);

async function uploaded(api: DocumentsApi, set: DocSet = 'before') {
	const session = new UploadSession(api);
	session.add(set, [docx()]);
	await vi.waitFor(() => expect(session.items[0].status).toBe('done'));
	return { session, item: session.items[0] };
}

describe('UploadSession.add', () => {
	it('uploads accepted files into their set and returns rejected names', async () => {
		const api = fakeApi();
		const session = new UploadSession(api);

		const rejected = session.add('after', [docx('a.pdf'), new File([''], 'notes.txt')]);

		expect(rejected).toEqual(['notes.txt']);
		expect(session.itemsIn('after').map((item) => item.file.name)).toEqual(['a.pdf']);
		expect(session.itemsIn('before')).toEqual([]);
		await vi.waitFor(() => expect(session.items[0].status).toBe('done'));
		expect(session.items[0].document?.id).toBe('id-a.pdf');
		expect(api.upload).toHaveBeenCalledWith(expect.any(File), 'after', expect.any(Function));
	});

	it('reports processing once every byte is sent', () => {
		let finish: (document: ApiDocument) => void = () => {};
		const api = fakeApi({
			upload: (file, set, onProgress) => {
				onProgress(1);
				return new Promise((resolve) => (finish = resolve));
			}
		});
		const session = new UploadSession(api);

		session.add('before', [docx()]);

		const [item] = session.items;
		expect(item.status).toBe('processing');
		expect(item.progress).toBe(1);
		expect(item.inFlight).toBe(true);
		finish(storedDocument(item.file, 'before'));
	});

	it('marks a failed upload retriable only for network and server errors', async () => {
		const api = fakeApi({
			upload: vi
				.fn()
				.mockRejectedValueOnce(new ApiError('Формат .doc не поддерживается', 415))
				.mockRejectedValueOnce(new ApiError('Сервер недоступен', 0))
		});
		const session = new UploadSession(api);

		session.add('before', [docx('old.doc'), docx('b.docx')]);

		await vi.waitFor(() =>
			expect(session.items.every((item) => item.status === 'failed')).toBe(true)
		);
		const [unsupported, offline] = session.items;
		expect(unsupported.error).toBe('Формат .doc не поддерживается');
		expect(unsupported.retriable).toBe(false);
		expect(offline.retriable).toBe(true);
	});
});

describe('UploadSession.retry', () => {
	it('sends a failed file again', async () => {
		const upload = vi
			.fn<DocumentsApi['upload']>()
			.mockRejectedValueOnce(new ApiError('Сервер недоступен', 0))
			.mockImplementationOnce(async (file, set) => storedDocument(file, set));
		const session = new UploadSession(fakeApi({ upload }));
		session.add('before', [docx()]);
		await vi.waitFor(() => expect(session.items[0].status).toBe('failed'));

		session.retry(session.items[0]);

		await vi.waitFor(() => expect(session.items[0].status).toBe('done'));
		expect(session.items[0].error).toBeNull();
		expect(upload).toHaveBeenCalledTimes(2);
	});
});

describe('UploadSession.setType', () => {
	it('stores the type the backend confirms', async () => {
		const api = fakeApi();
		const { session, item } = await uploaded(api);

		await session.setType(item, 'job_description');

		expect(api.setType).toHaveBeenCalledWith('id-Положение_ред_9.docx', 'job_description');
		expect(item.document?.doc_type).toBe('job_description');
		expect(item.busy).toBe(false);
	});

	it('reverts the type and shows the error when the backend refuses', async () => {
		const api = fakeApi({
			setType: vi.fn().mockRejectedValue(new ApiError('Документ не найден', 404))
		});
		const { session, item } = await uploaded(api);

		await session.setType(item, 'order');

		expect(item.document?.doc_type).toBe('unit_regulation');
		expect(item.error).toBe('Документ не найден');
	});
});

describe('UploadSession.remove', () => {
	it('deletes the stored document and drops the file', async () => {
		const api = fakeApi();
		const { session, item } = await uploaded(api);

		await session.remove(item);

		expect(api.remove).toHaveBeenCalledWith('id-Положение_ред_9.docx');
		expect(session.items).toEqual([]);
	});

	it('drops the file when the document is already gone', async () => {
		const api = fakeApi({
			remove: vi.fn().mockRejectedValue(new ApiError('Документ не найден', 404))
		});
		const { session, item } = await uploaded(api);

		await session.remove(item);

		expect(session.items).toEqual([]);
	});

	it('keeps the file and shows the error when deletion fails', async () => {
		const api = fakeApi({
			remove: vi.fn().mockRejectedValue(new ApiError('Сервер недоступен', 0))
		});
		const { session, item } = await uploaded(api);

		await session.remove(item);

		expect(session.items).toEqual([item]);
		expect(item.error).toBe('Сервер недоступен');
		expect(item.busy).toBe(false);
	});

	it('drops a failed upload without calling the backend', async () => {
		const api = fakeApi({
			upload: vi.fn().mockRejectedValue(new ApiError('Файл больше 20 МБ', 413))
		});
		const session = new UploadSession(api);
		session.add('before', [docx()]);
		await vi.waitFor(() => expect(session.items[0].status).toBe('failed'));

		await session.remove(session.items[0]);

		expect(api.remove).not.toHaveBeenCalled();
		expect(session.items).toEqual([]);
	});
});
