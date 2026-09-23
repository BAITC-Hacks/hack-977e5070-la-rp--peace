import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DocumentsApi } from '$lib/api/client';
import { ApiError } from '$lib/api/errors';
import type { DocSet, DocumentOut } from '$lib/api/types';

import { POLL_INTERVAL_MS, UploadSession } from './session.svelte';
import { UPLOAD_SESSION_KEY, type SessionStorage } from './persistence';

const DOCUMENT_ID = 7;

function storedDocument(overrides: Partial<DocumentOut> = {}): DocumentOut {
	return {
		id: DOCUMENT_ID,
		file_name: 'Положение_ред_9.docx',
		set: 'before',
		source_format: 'docx',
		file_size_bytes: 7,
		content_sha256: 'ab12',
		uploaded_at: '2026-09-23T10:00:00Z',
		parse_status: 'pending',
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
		node_count: 0,
		blocking_issues: 0,
		other_issues: 0,
		...overrides
	};
}

const validated = storedDocument({
	parse_status: 'validated',
	document_type: 'Положение о подразделении',
	node_count: 42
});

/**
 * A backend double: the upload is accepted as `pending`, and every later read reports the
 * document parsed.
 */
function fakeApi(overrides: Partial<DocumentsApi> = {}): DocumentsApi {
	return {
		upload: vi.fn(async (file: File, set: DocSet, onProgress: (fraction: number) => void) => {
			onProgress(0.5);
			onProgress(1);
			return storedDocument({ file_name: file.name, set });
		}),
		get: vi.fn(async () => validated),
		setType: vi.fn(async (id: number, documentType: string) =>
			storedDocument({ ...validated, id, document_type: documentType })
		),
		remove: vi.fn(async () => undefined),
		...overrides
	};
}

const docx = (name = 'Положение_ред_9.docx') => new File(['content'], name);

/** Lets pending promises settle without moving the clock. */
const settle = () => vi.advanceTimersByTimeAsync(0);
const nextPoll = () => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);

async function parsedItem(api: DocumentsApi) {
	const session = new UploadSession(api);
	session.add('before', [docx()]);
	await nextPoll();
	const [item] = session.items;
	expect(item.status).toBe('parsed');
	return { session, item };
}

beforeEach(() => {
	vi.useFakeTimers();
});

afterEach(() => {
	vi.useRealTimers();
});

describe('UploadSession.add', () => {
	it('uploads accepted files into their set and returns rejected names', async () => {
		const api = fakeApi();
		const session = new UploadSession(api);

		const rejected = session.add('after', [docx('a.pdf'), new File([''], 'notes.txt')]);
		await settle();

		expect(rejected).toEqual(['notes.txt']);
		expect(session.itemsIn('after').map((item) => item.name)).toEqual(['a.pdf']);
		expect(session.itemsIn('before')).toEqual([]);
		expect(session.items[0].document?.id).toBe(DOCUMENT_ID);
		expect(api.upload).toHaveBeenCalledWith(expect.any(File), 'after', expect.any(Function));
	});

	it('shows the share of bytes sent until the backend answers', () => {
		const api = fakeApi({
			upload: (file, set, onProgress) => {
				onProgress(0.42);
				return new Promise<DocumentOut>(() => {});
			}
		});
		const session = new UploadSession(api);

		session.add('before', [docx()]);

		const [item] = session.items;
		expect(item.status).toBe('uploading');
		expect(item.statusLabel).toBe('Загрузка 42%');
		expect(item.removable).toBe(false);
	});
});

describe('UploadSession polling', () => {
	it('follows a document from pending to validated', async () => {
		const get = vi
			.fn<DocumentsApi['get']>()
			.mockResolvedValueOnce(storedDocument())
			.mockResolvedValueOnce(validated);
		const api = fakeApi({ get });
		const session = new UploadSession(api);

		session.add('before', [docx()]);
		await settle();

		const [item] = session.items;
		expect(item.status).toBe('parsing');
		expect(item.statusLabel).toBe('Разбирается…');
		expect(get).not.toHaveBeenCalled();

		await nextPoll();
		expect(get).toHaveBeenCalledTimes(1);
		expect(get).toHaveBeenCalledWith(DOCUMENT_ID);
		expect(item.status).toBe('parsing');

		await nextPoll();
		expect(get).toHaveBeenCalledTimes(2);
		expect(item.status).toBe('parsed');
		expect(item.statusLabel).toBe('Разобран');
		expect(item.document?.node_count).toBe(42);

		await vi.advanceTimersByTimeAsync(10 * POLL_INTERVAL_MS);
		expect(get).toHaveBeenCalledTimes(2);
	});

	it('ends in needs_review with the issue counts', async () => {
		const review = storedDocument({
			parse_status: 'needs_review',
			blocking_issues: 1,
			other_issues: 3
		});
		const session = new UploadSession(fakeApi({ get: vi.fn(async () => review) }));

		session.add('before', [docx()]);
		await nextPoll();

		const [item] = session.items;
		expect(item.status).toBe('needs_review');
		expect(item.statusLabel).toBe('Требует проверки');
		expect(item.parsed).toBe(true);
		expect(item.document?.blocking_issues).toBe(1);
		expect(item.document?.other_issues).toBe(3);
	});

	it('stops once the file is removed', async () => {
		const get = vi.fn(async () => storedDocument());
		const api = fakeApi({ get });
		const session = new UploadSession(api);
		session.add('before', [docx()]);
		await nextPoll();
		expect(get).toHaveBeenCalledTimes(1);

		await session.remove(session.items[0]);

		expect(api.remove).toHaveBeenCalledWith(DOCUMENT_ID);
		expect(session.items).toEqual([]);
		await vi.advanceTimersByTimeAsync(10 * POLL_INTERVAL_MS);
		expect(get).toHaveBeenCalledTimes(1);
	});

	it('stops once the session is disposed', async () => {
		const get = vi.fn(async () => storedDocument());
		const session = new UploadSession(fakeApi({ get }));
		session.add('before', [docx()]);
		await settle();

		session.dispose();

		await vi.advanceTimersByTimeAsync(10 * POLL_INTERVAL_MS);
		expect(get).not.toHaveBeenCalled();
	});

	it('fails on a lost connection and resumes polling on retry', async () => {
		const get = vi
			.fn<DocumentsApi['get']>()
			.mockRejectedValueOnce(new ApiError('Сервер недоступен', 0))
			.mockResolvedValueOnce(validated);
		const api = fakeApi({ get });
		const session = new UploadSession(api);
		session.add('before', [docx()]);
		await nextPoll();

		const [item] = session.items;
		expect(item.status).toBe('failed');
		expect(item.error).toBe('Сервер недоступен');
		expect(item.retriable).toBe(true);

		session.retry(item);
		await nextPoll();

		expect(item.status).toBe('parsed');
		expect(item.error).toBeNull();
		expect(api.upload).toHaveBeenCalledTimes(1);
	});
});

describe('UploadSession upload errors', () => {
	it('keeps the file with the backend message when parsing is not configured', async () => {
		const message = 'Разбор недоступен: не заданы OPENAI_API_KEY и OPENAI_MODEL';
		const api = fakeApi({ upload: vi.fn().mockRejectedValue(new ApiError(message, 503)) });
		const session = new UploadSession(api);

		session.add('before', [docx()]);
		await settle();

		const [item] = session.items;
		expect(item.status).toBe('failed');
		expect(item.error).toBe(message);
		expect(item.retriable).toBe(true);
		expect(item.document).toBeNull();
		expect(api.get).not.toHaveBeenCalled();
	});

	it('marks a failed upload retriable only for network and server errors', async () => {
		const api = fakeApi({
			upload: vi
				.fn()
				.mockRejectedValueOnce(new ApiError('Формат .doc не поддерживается', 415))
				.mockRejectedValueOnce(new ApiError('Файл больше 20 МБ', 413))
				.mockRejectedValueOnce(new ApiError('Сервер недоступен', 0))
		});
		const session = new UploadSession(api);

		session.add('before', [docx('old.doc'), docx('big.pdf'), docx('b.docx')]);
		await settle();

		const [unsupported, tooLarge, offline] = session.items;
		expect(session.items.every((item) => item.status === 'failed')).toBe(true);
		expect(unsupported.error).toBe('Формат .doc не поддерживается');
		expect(unsupported.retriable).toBe(false);
		expect(tooLarge.retriable).toBe(false);
		expect(offline.retriable).toBe(true);
	});

	it('sends a failed file again on retry', async () => {
		const upload = vi
			.fn<DocumentsApi['upload']>()
			.mockRejectedValueOnce(new ApiError('Сервер недоступен', 0))
			.mockImplementationOnce(async () => storedDocument());
		const session = new UploadSession(fakeApi({ upload }));
		session.add('before', [docx()]);
		await settle();
		expect(session.items[0].status).toBe('failed');

		session.retry(session.items[0]);
		await nextPoll();

		expect(session.items[0].status).toBe('parsed');
		expect(session.items[0].error).toBeNull();
		expect(upload).toHaveBeenCalledTimes(2);
	});
});

describe('UploadSession.setType', () => {
	it('stores the trimmed type the backend confirms', async () => {
		const api = fakeApi();
		const { session, item } = await parsedItem(api);

		await session.setType(item, '  Должностная инструкция ');

		expect(api.setType).toHaveBeenCalledWith(DOCUMENT_ID, 'Должностная инструкция');
		expect(item.document?.document_type).toBe('Должностная инструкция');
		expect(item.busy).toBe(false);
	});

	it('ignores an empty or unchanged type', async () => {
		const api = fakeApi();
		const { session, item } = await parsedItem(api);

		await session.setType(item, '   ');
		await session.setType(item, 'Положение о подразделении');

		expect(api.setType).not.toHaveBeenCalled();
	});

	it('waits for parsing to end, since the parser sets the type itself', async () => {
		const api = fakeApi();
		const session = new UploadSession(api);
		session.add('before', [docx()]);
		await settle();

		await session.setType(session.items[0], 'ВНД');

		expect(api.setType).not.toHaveBeenCalled();
	});

	it('reverts the type and shows the error when the backend refuses', async () => {
		const api = fakeApi({
			setType: vi.fn().mockRejectedValue(new ApiError('Документ не найден', 404))
		});
		const { session, item } = await parsedItem(api);

		await session.setType(item, 'ВНД');

		expect(item.document?.document_type).toBe('Положение о подразделении');
		expect(item.error).toBe('Документ не найден');
	});
});

describe('UploadSession.remove', () => {
	it('deletes the stored document and drops the file', async () => {
		const api = fakeApi();
		const { session, item } = await parsedItem(api);

		await session.remove(item);

		expect(api.remove).toHaveBeenCalledWith(DOCUMENT_ID);
		expect(session.items).toEqual([]);
	});

	it('drops the file when the document is already gone', async () => {
		const api = fakeApi({
			remove: vi.fn().mockRejectedValue(new ApiError('Документ не найден', 404))
		});
		const { session, item } = await parsedItem(api);

		await session.remove(item);

		expect(session.items).toEqual([]);
	});

	it('keeps the file and shows the error when deletion fails', async () => {
		const api = fakeApi({
			remove: vi.fn().mockRejectedValue(new ApiError('Сервер недоступен', 0))
		});
		const { session, item } = await parsedItem(api);

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
		await settle();

		await session.remove(session.items[0]);

		expect(api.remove).not.toHaveBeenCalled();
		expect(session.items).toEqual([]);
	});
});

function memoryStorage(initial: string | null = null): SessionStorage {
	const values = new Map<string, string>();
	if (initial !== null) values.set(UPLOAD_SESSION_KEY, initial);
	return {
		getItem: vi.fn((key) => values.get(key) ?? null),
		setItem: vi.fn((key, next: string) => {
			values.set(key, next);
		})
	};
}

const savedUpload = { id: DOCUMENT_ID, set: 'before', name: 'Положение_ред_9.docx', size: 7 };
const snapshot = () => JSON.stringify({ version: 1, items: [savedUpload] });

describe('UploadSession persistence', () => {
	it('does not restore document ids saved for a different backend', async () => {
		const storage = memoryStorage();
		const original = new UploadSession(fakeApi(), () => storage, 'backend-a');
		original.add('before', [docx()]);
		await settle();
		original.dispose();
		const api = fakeApi();
		const otherBackend = new UploadSession(api, () => storage, 'backend-b');
		await otherBackend.restore();
		expect(otherBackend.items).toEqual([]);
		expect(api.get).not.toHaveBeenCalled();
		const sameBackend = new UploadSession(api, () => storage, 'backend-a');
		await sameBackend.restore();
		expect(sameBackend.items[0].documentId).toBe(DOCUMENT_ID);
	});

	it('restores the selected documents after reload, rechecks their state and resumes polling', async () => {
		const storage = memoryStorage();
		const original = new UploadSession(fakeApi(), () => storage);
		original.add('before', [docx()]);
		await settle();
		expect(JSON.parse(storage.getItem(UPLOAD_SESSION_KEY)!)).toEqual({
			version: 1,
			items: [savedUpload]
		});
		original.dispose();
		const api = fakeApi({
			get: vi
				.fn<DocumentsApi['get']>()
				.mockResolvedValueOnce(storedDocument())
				.mockResolvedValueOnce(validated)
		});
		const reloaded = new UploadSession(api, () => storage);

		await reloaded.restore();
		expect(api.get).toHaveBeenCalledWith(DOCUMENT_ID);
		expect(api.upload).not.toHaveBeenCalled();
		expect(reloaded.items[0].file).toBeNull();
		expect(reloaded.items[0].name).toBe(savedUpload.name);
		expect(reloaded.items[0].size).toBe(savedUpload.size);
		expect(reloaded.items[0].status).toBe('parsing');
		expect(reloaded.restoring).toBe(false);

		await nextPoll();
		expect(reloaded.items[0].status).toBe('parsed');
		expect(api.get).toHaveBeenCalledTimes(2);
	});

	it('does not restore file bytes that had not reached the backend', async () => {
		const storage = memoryStorage();
		const api = fakeApi({ upload: vi.fn(() => new Promise<DocumentOut>(() => {})) });
		const original = new UploadSession(api, () => storage);
		original.add('before', [docx()]);
		original.dispose();
		const reloadedApi = fakeApi();
		const reloaded = new UploadSession(reloadedApi, () => storage);
		await reloaded.restore();
		expect(reloaded.items).toEqual([]);
		expect(reloadedApi.upload).not.toHaveBeenCalled();
		expect(reloadedApi.get).not.toHaveBeenCalled();
	});

	it('restores only once even when called again during an outstanding read', async () => {
		let resolveRead!: (document: DocumentOut) => void;
		const api = fakeApi({
			get: vi.fn(
				() =>
					new Promise<DocumentOut>((resolve) => {
						resolveRead = resolve;
					})
			)
		});
		const storage = memoryStorage(snapshot());
		const session = new UploadSession(api, () => storage);
		const restoring = session.restore();
		expect(session.restore()).toBe(restoring);
		expect(session.restoring).toBe(true);
		expect(session.items).toHaveLength(1);
		resolveRead(validated);
		await restoring;
		await session.restore();
		expect(api.get).toHaveBeenCalledTimes(1);
		expect(session.restoring).toBe(false);
	});

	it('keeps a missing document visible as an error until removal, without re-uploading it', async () => {
		const api = fakeApi({
			get: vi.fn().mockRejectedValue(new ApiError('Документ не найден', 404)),
			remove: vi.fn().mockRejectedValue(new ApiError('Документ не найден', 404))
		});
		const storage = memoryStorage(snapshot());
		const session = new UploadSession(api, () => storage);
		await session.restore();
		const [item] = session.items;
		expect(item.status).toBe('failed');
		expect(item.error).toBe('Документ не найден');
		expect(item.retriable).toBe(false);
		session.retry(item);
		expect(api.get).toHaveBeenCalledTimes(1);
		expect(api.upload).not.toHaveBeenCalled();
		await session.remove(item);
		const reloaded = new UploadSession(api, () => storage);
		await reloaded.restore();
		expect(reloaded.items).toEqual([]);
	});

	it('retries the stored id after a network failure even though no document was read yet', async () => {
		const api = fakeApi({
			get: vi
				.fn<DocumentsApi['get']>()
				.mockRejectedValueOnce(new ApiError('Сервер недоступен', 0))
				.mockResolvedValueOnce(validated)
		});
		const storage = memoryStorage(snapshot());
		const session = new UploadSession(api, () => storage);
		await session.restore();
		const [item] = session.items;
		expect(item.document).toBeNull();
		expect(item.retriable).toBe(true);
		session.retry(item);
		await settle();
		expect(item.status).toBe('parsed');
		expect(api.get).toHaveBeenCalledTimes(2);
		expect(api.upload).not.toHaveBeenCalled();
	});

	it('does not revive a removed item when its restoration request finishes late', async () => {
		let resolveRead!: (document: DocumentOut) => void;
		const api = fakeApi({
			get: vi.fn(
				() =>
					new Promise<DocumentOut>((resolve) => {
						resolveRead = resolve;
					})
			)
		});
		const storage = memoryStorage(snapshot());
		const session = new UploadSession(api, () => storage);
		const restoring = session.restore();
		await session.remove(session.items[0]);
		resolveRead(storedDocument());
		await restoring;
		await nextPoll();
		expect(session.items).toEqual([]);
		expect(api.get).toHaveBeenCalledTimes(1);
		const reloaded = new UploadSession(api, () => storage);
		await reloaded.restore();
		expect(reloaded.items).toEqual([]);
	});

	it('retains saved ids if deletion fails', async () => {
		const api = fakeApi({
			remove: vi.fn().mockRejectedValue(new ApiError('Сервер недоступен', 0))
		});
		const storage = memoryStorage(snapshot());
		const session = new UploadSession(api, () => storage);
		await session.restore();
		await session.remove(session.items[0]);
		const reloaded = new UploadSession(api, () => storage);
		await reloaded.restore();
		expect(reloaded.items).toHaveLength(1);
		expect(reloaded.items[0].documentId).toBe(DOCUMENT_ID);
	});

	it('ignores corrupted storage and continues uploading when storage is blocked', async () => {
		const corruptedApi = fakeApi();
		const corrupted = new UploadSession(corruptedApi, () => memoryStorage('{'));
		await corrupted.restore();
		expect(corrupted.items).toEqual([]);
		expect(corruptedApi.get).not.toHaveBeenCalled();

		const warning = vi.spyOn(console, 'warn').mockImplementation(() => {});
		const blocked = new UploadSession(fakeApi(), () => {
			throw new Error('Storage disabled');
		});
		await blocked.restore();
		blocked.add('before', [docx()]);
		await nextPoll();
		expect(blocked.items[0].status).toBe('parsed');
		expect(warning).toHaveBeenCalledTimes(2);
		warning.mockRestore();
	});
});
