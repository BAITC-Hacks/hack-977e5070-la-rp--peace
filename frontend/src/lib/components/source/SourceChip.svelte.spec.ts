import { describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';

import type { SourcesApi } from '$lib/api/sources';
import { SourcePanelState, type SourceTarget } from '$lib/source/panel.svelte';

import SourceChip from './SourceChip.svelte';

const targets: SourceTarget[] = [{ nodeId: 11 }, { nodeId: 22, quote: 'проводит аудит' }];

/** A panel whose backend never answers: the chip does not care what the panel shows. */
function idlePanel() {
	const api: SourcesApi = {
		getNodeSource: vi.fn<SourcesApi['getNodeSource']>(() => new Promise(() => {})),
		resolveSource: vi.fn<SourcesApi['resolveSource']>(() => new Promise(() => {})),
		fileUrl: (documentId: number) => `/files/${documentId}`
	};
	return new SourcePanelState(api);
}

describe('SourceChip', () => {
	it('names the side and the clause and shows the quote on hover', async () => {
		await render(SourceChip, {
			props: { panel: idlePanel(), targets, index: 1, set: 'after', anchor: 'п. 3.4' }
		});

		const chip = page.getByRole('button', { name: 'После · п. 3.4' });
		await expect.element(chip).toBeVisible();
		await expect.element(chip).toHaveAttribute('title', '«проводит аудит»');
		await expect.element(chip).toHaveClass(/font-mono/);
	});

	it('opens the panel at its own citation', async () => {
		const panel = idlePanel();
		const open = vi.spyOn(panel, 'open');
		await render(SourceChip, {
			props: { panel, targets, index: 1, set: 'after', anchor: 'п. 3.4' }
		});

		await page.getByRole('button', { name: 'После · п. 3.4' }).click();

		expect(open).toHaveBeenCalledWith(targets, 1);
		expect(panel.isOpen).toBe(true);
		expect(panel.current).toEqual(targets[1]);
	});
});
