import { describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';

import { ApiError } from '$lib/api/errors';
import type { SourceRef, SourcesApi } from '$lib/api/sources';
import { SourcePanelState, type SourceTarget } from '$lib/source/panel.svelte';

import SourceChip from './SourceChip.svelte';
import SourcePanel from './SourcePanel.svelte';

const sources: Record<number, SourceRef> = {
	11: {
		node_id: 11,
		document_id: 1,
		document_name: 'Положение_СВА_ред_8.docx',
		set: 'before',
		anchor: 'п. 2.5',
		path: 'Разд. 2 «Функции» › п. 2.5',
		location: { paragraph: 40 },
		quote: 'проводит аудит системы защиты информации',
		context: '2.5. Служба внутреннего аудита проводит аудит системы защиты информации.',
		start: 31,
		end: 71
	},
	22: {
		node_id: 22,
		document_id: 2,
		document_name: 'Положение_ДИБиР_ред_9.pdf',
		set: 'after',
		anchor: 'п. 2.8',
		path: 'Разд. 2 «Функции» › п. 2.8',
		location: { page: 6 },
		quote: 'проводит аудит информационной безопасности',
		context: '2.8. Департамент проводит аудит информационной безопасности.',
		start: 17,
		end: 59
	}
};

const targets: SourceTarget[] = [
	{ nodeId: 11, quote: 'проводит аудит системы защиты информации' },
	{ nodeId: 22, quote: 'проводит аудит информационной безопасности' }
];

function fakeApi(overrides: Partial<SourcesApi> = {}): SourcesApi {
	return {
		getNodeSource: vi.fn(async (nodeId: number) => sources[nodeId]),
		resolveSource: vi.fn(async (nodeId: number) => sources[nodeId]),
		fileUrl: (documentId: number) => `http://api.test/api/documents/${documentId}/file`,
		...overrides
	};
}

async function renderPanel(api: SourcesApi) {
	const panel = new SourcePanelState(api);
	await render(SourcePanel, { props: { panel } });
	await render(SourceChip, {
		props: { panel, targets, index: 0, set: 'before', anchor: 'п. 2.5' }
	});
	return panel;
}

const dialogElement = () => document.querySelector('dialog') as HTMLDialogElement;

describe('SourcePanel', () => {
	it('opens from a chip, pages through the sources and closes on Esc', async () => {
		await renderPanel(fakeApi());
		const chip = page.getByRole('button', { name: 'До · п. 2.5' });

		await chip.click();

		const dialog = page.getByRole('dialog', { name: 'Положение_СВА_ред_8.docx' });
		await expect.element(dialog).toBeVisible();
		await expect.element(dialog.getByText('Разд. 2 «Функции» › п. 2.5')).toBeVisible();
		await expect.element(dialog.getByText('абзац 41')).toBeVisible();
		await expect.element(dialog.getByText('1 из 2')).toBeVisible();
		const mark = dialog.getByText('проводит аудит системы защиты информации', { exact: true });
		await expect.element(mark).toBeVisible();
		expect(mark.element().tagName).toBe('MARK');
		await expect
			.element(dialog.getByRole('link', { name: 'Скачать оригинал' }))
			.toHaveAttribute('href', 'http://api.test/api/documents/1/file');

		await page.getByRole('button', { name: 'Следующий источник' }).click();

		await expect
			.element(page.getByRole('heading', { name: 'Положение_ДИБиР_ред_9.pdf' }))
			.toBeVisible();
		await expect.element(page.getByText('стр. 6')).toBeVisible();
		await expect.element(page.getByText('После', { exact: true })).toBeVisible();
		await expect
			.element(page.getByRole('button', { name: 'Следующий источник' }))
			.toHaveAttribute('aria-disabled', 'true');

		await userEvent.keyboard('{ArrowLeft}');

		await expect
			.element(page.getByRole('heading', { name: 'Положение_СВА_ред_8.docx' }))
			.toBeVisible();

		await userEvent.keyboard('{Escape}');

		await expect.poll(() => dialogElement().open).toBe(false);
		await expect.poll(() => document.activeElement).toBe(chip.element());
	});

	it('closes with «×» and returns focus to the chip', async () => {
		const panel = await renderPanel(fakeApi());
		const chip = page.getByRole('button', { name: 'До · п. 2.5' });
		await chip.click();
		await expect.element(page.getByRole('dialog')).toBeVisible();

		await page.getByRole('button', { name: 'Закрыть' }).click();

		await expect.poll(() => dialogElement().open).toBe(false);
		expect(panel.isOpen).toBe(false);
		await expect.poll(() => document.activeElement).toBe(chip.element());
	});

	it('warns instead of quoting when the document does not contain the quote', async () => {
		await renderPanel(
			fakeApi({
				resolveSource: vi
					.fn()
					.mockRejectedValue(
						new ApiError(
							'Цитата не найдена в тексте: «проводит аудит системы защиты информации»',
							422
						)
					)
			})
		);

		await page.getByRole('button', { name: 'До · п. 2.5' }).click();

		const warning = page.getByRole('alert');
		await expect
			.element(warning)
			.toHaveTextContent('Цитата не найдена в документе — вывод не подтверждён');
		await expect.element(warning).toHaveClass(/bg-warn-soft/);
		expect(dialogElement().querySelector('mark')).toBeNull();
		await expect
			.element(page.getByRole('link', { name: 'Скачать оригинал' }))
			.not.toBeInTheDocument();
	});
});
