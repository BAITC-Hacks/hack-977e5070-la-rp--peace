import { afterEach, describe, expect, it, vi } from 'vitest';

import { documentApi, fileUrl } from './document';
import { ApiError, NETWORK_ERROR_MESSAGE } from './errors';

function stubFetch(response: Response | Error) {
	const fetch = vi.fn(async () => {
		if (response instanceof Error) {
			throw response;
		}
		return response;
	});
	vi.stubGlobal('fetch', fetch);
	return fetch;
}

const json = (body: unknown, status = 200) =>
	new Response(JSON.stringify(body), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('documentApi', () => {
	it.each([
		['get', 'http://localhost:8000/api/documents/7'],
		['nodes', 'http://localhost:8000/api/documents/7/nodes'],
		['issues', 'http://localhost:8000/api/documents/7/issues'],
		['profile', 'http://localhost:8000/api/documents/7/profile']
	] as const)('%s reads %s', async (method, url) => {
		const fetch = stubFetch(json({ answer: method }));

		const result = await documentApi[method](7);

		expect(fetch).toHaveBeenCalledWith(url);
		expect(result).toEqual({ answer: method });
	});

	it('throws the backend message with the status', async () => {
		stubFetch(json({ detail: 'Документ не найден' }, 404));

		const failure = documentApi.get(7);

		await expect(failure).rejects.toThrow(new ApiError('Документ не найден', 404));
		await expect(failure).rejects.toMatchObject({ status: 404 });
	});

	it('reports an unreachable server as status 0', async () => {
		stubFetch(new TypeError('Failed to fetch'));

		await expect(documentApi.nodes(7)).rejects.toMatchObject({
			message: NETWORK_ERROR_MESSAGE,
			status: 0
		});
	});
});

describe('fileUrl', () => {
	it('points at the original file download', () => {
		expect(fileUrl(12)).toBe('http://localhost:8000/api/documents/12/file');
	});
});
