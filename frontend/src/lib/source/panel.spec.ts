import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '$lib/api/errors';
import type { SourceRef, SourcesApi } from '$lib/api/sources';

import { SourcePanelState, type SourceTarget } from './panel.svelte';

function sourceOf(nodeId: number, quote?: string): SourceRef {
	const context = `${nodeId}. Служба проводит аудит системы защиты информации.`;
	const cited = quote ?? context;
	const start = context.indexOf(cited);
	return {
		node_id: nodeId,
		document_id: 3,
		document_name: 'Положение_ред_9.pdf',
		set: 'after',
		anchor: `п. ${nodeId}`,
		path: `Разд. 1 › п. ${nodeId}`,
		location: { page: nodeId },
		quote: cited,
		context,
		start,
		end: start + cited.length
	};
}

/** A backend double that finds every quote. */
function fakeApi(overrides: Partial<SourcesApi> = {}): SourcesApi {
	return {
		getNodeSource: vi.fn(async (nodeId: number) => sourceOf(nodeId)),
		resolveSource: vi.fn(async (nodeId: number, quote: string) => sourceOf(nodeId, quote)),
		fileUrl: (documentId: number) => `/files/${documentId}`,
		...overrides
	};
}

/** A promise settled from the outside, to control the order in which answers arrive. */
function deferred<T>() {
	let resolve: (value: T) => void = () => {};
	const promise = new Promise<T>((settle) => (resolve = settle));
	return { promise, resolve };
}

const targets: SourceTarget[] = [
	{ nodeId: 1, quote: 'проводит аудит' },
	{ nodeId: 2 },
	{ nodeId: 3, quote: 'защиты информации' }
];

describe('SourcePanelState.open', () => {
	it('verifies a quoted citation and shows it', async () => {
		const api = fakeApi();
		const panel = new SourcePanelState(api);

		const loaded = panel.open(targets, 0);

		expect(panel.isOpen).toBe(true);
		expect(panel.status).toBe('loading');
		await loaded;
		expect(api.resolveSource).toHaveBeenCalledWith(1, 'проводит аудит');
		expect(panel.status).toBe('ready');
		expect(panel.source?.quote).toBe('проводит аудит');
		expect(panel.current).toEqual(targets[0]);
		expect(panel.downloadUrl).toBe('/files/3');
	});

	it('reads the whole node when the citation has no quote', async () => {
		const api = fakeApi();
		const panel = new SourcePanelState(api);

		await panel.open(targets, 1);

		expect(api.getNodeSource).toHaveBeenCalledWith(2);
		expect(api.resolveSource).not.toHaveBeenCalled();
		expect(panel.source?.node_id).toBe(2);
	});

	it('keeps the index within the citations', async () => {
		const panel = new SourcePanelState(fakeApi());

		await panel.open(targets, 7);
		expect(panel.index).toBe(2);

		await panel.open(targets, -1);
		expect(panel.index).toBe(0);
	});

	it('stays closed without citations', async () => {
		const api = fakeApi();
		const panel = new SourcePanelState(api);

		await panel.open([]);

		expect(panel.isOpen).toBe(false);
		expect(api.getNodeSource).not.toHaveBeenCalled();
	});
});

describe('SourcePanelState.prev / next', () => {
	it('moves between the citations and stops at the ends', async () => {
		const panel = new SourcePanelState(fakeApi());
		await panel.open(targets, 0);
		expect(panel.hasPrev).toBe(false);

		await panel.next();
		expect(panel.source?.node_id).toBe(2);
		await panel.next();
		expect(panel.source?.node_id).toBe(3);
		expect(panel.hasNext).toBe(false);

		await panel.next();
		expect(panel.index).toBe(2);

		await panel.prev();
		expect(panel.index).toBe(1);
		expect(panel.hasPrev).toBe(true);
	});

	it('drops the answer for a citation the user has already left', async () => {
		const slow = deferred<SourceRef>();
		const api = fakeApi({
			resolveSource: vi.fn(async (nodeId: number, quote: string) =>
				nodeId === 1 ? slow.promise : sourceOf(nodeId, quote)
			)
		});
		const panel = new SourcePanelState(api);

		const first = panel.open(targets, 0);
		await panel.next();
		slow.resolve(sourceOf(1, 'проводит аудит'));
		await first;

		expect(panel.index).toBe(1);
		expect(panel.source?.node_id).toBe(2);
	});
});

describe('SourcePanelState errors', () => {
	it('flags a quote the document does not contain as unconfirmed', async () => {
		const api = fakeApi({
			resolveSource: vi
				.fn()
				.mockRejectedValue(new ApiError('Цитата не найдена в тексте: «проводит аудит»', 422))
		});
		const panel = new SourcePanelState(api);

		await panel.open(targets, 0);

		expect(panel.status).toBe('not_found');
		expect(panel.source).toBeNull();
		expect(panel.downloadUrl).toBeNull();
		expect(panel.error).toBeNull();
	});

	it('shows other failures and retries the ones that can succeed', async () => {
		const getNodeSource = vi
			.fn<SourcesApi['getNodeSource']>()
			.mockRejectedValueOnce(new ApiError('Сервер недоступен', 0))
			.mockImplementationOnce(async (nodeId) => sourceOf(nodeId));
		const panel = new SourcePanelState(fakeApi({ getNodeSource }));

		await panel.open(targets, 1);

		expect(panel.status).toBe('failed');
		expect(panel.error).toBe('Сервер недоступен');
		expect(panel.retriable).toBe(true);

		await panel.retry();

		expect(panel.status).toBe('ready');
		expect(panel.error).toBeNull();
		expect(getNodeSource).toHaveBeenCalledTimes(2);
	});

	it('does not offer to retry a missing node', async () => {
		const api = fakeApi({
			getNodeSource: vi.fn().mockRejectedValue(new ApiError('Узел 2 не найден', 404))
		});
		const panel = new SourcePanelState(api);

		await panel.open(targets, 1);

		expect(panel.status).toBe('failed');
		expect(panel.retriable).toBe(false);
	});
});

describe('SourcePanelState.close', () => {
	it('clears the panel and ignores an answer still on its way', async () => {
		const slow = deferred<SourceRef>();
		const panel = new SourcePanelState(fakeApi({ resolveSource: () => slow.promise }));

		const loaded = panel.open(targets, 0);
		panel.close();
		slow.resolve(sourceOf(1, 'проводит аудит'));
		await loaded;

		expect(panel.isOpen).toBe(false);
		expect(panel.current).toBeNull();
		expect(panel.source).toBeNull();
	});
});
