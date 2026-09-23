import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './errors';
import { sourcesApi, type SourceRef } from './sources';

const source: SourceRef = {
	node_id: 7,
	document_id: 3,
	document_name: 'Положение_ред_9.pdf',
	set: 'after',
	anchor: 'п. 3.4',
	path: 'Разд. 3 «Структура» › п. 3.4',
	location: { page: 6 },
	quote: 'проводит аудит',
	context: '3.4. Служба проводит аудит системы.',
	start: 12,
	end: 26
};

function respond(status: number, body: unknown) {
	const fetchMock = vi.fn(async () => Response.json(body, { status }));
	vi.stubGlobal('fetch', fetchMock);
	return fetchMock;
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('sourcesApi.getNodeSource', () => {
	it('reads the node as a source', async () => {
		const fetchMock = respond(200, source);

		await expect(sourcesApi.getNodeSource(7)).resolves.toEqual(source);

		const [url] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toMatch(/\/api\/nodes\/7$/);
	});

	it('reports a missing node with the backend message', async () => {
		respond(404, { detail: 'Узел 7 не найден' });

		const error = await sourcesApi.getNodeSource(7).catch((reason: unknown) => reason);

		expect(error).toBeInstanceOf(ApiError);
		expect(error).toMatchObject({ status: 404, message: 'Узел 7 не найден' });
	});
});

describe('sourcesApi.resolveSource', () => {
	it('posts the citation', async () => {
		const fetchMock = respond(200, source);

		await expect(sourcesApi.resolveSource(7, 'проводит аудит')).resolves.toEqual(source);

		const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toMatch(/\/api\/sources\/resolve$/);
		expect(init.method).toBe('POST');
		expect(JSON.parse(String(init.body))).toEqual({ node_id: 7, quote: 'проводит аудит' });
	});

	it('rejects with 422 when the quote is not in the text', async () => {
		respond(422, { detail: 'Цитата не найдена в тексте: «проводит ревизию»' });

		const error = await sourcesApi.resolveSource(7, 'проводит ревизию').catch((r: unknown) => r);

		expect(error).toBeInstanceOf(ApiError);
		expect(error).toMatchObject({
			status: 422,
			message: 'Цитата не найдена в тексте: «проводит ревизию»'
		});
	});

	it('reports an unreachable server as status 0', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => {
				throw new TypeError('Failed to fetch');
			})
		);

		const error = await sourcesApi.resolveSource(7, 'аудит').catch((reason: unknown) => reason);

		expect(error).toMatchObject({ status: 0, retriable: true });
	});
});

describe('sourcesApi.fileUrl', () => {
	it('points at the original file download', () => {
		expect(sourcesApi.fileUrl(3)).toMatch(/\/api\/documents\/3\/file$/);
	});
});
