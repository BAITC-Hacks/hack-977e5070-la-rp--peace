import { describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';

import '../../routes/layout.css';
import type { DocumentsApi } from '$lib/api/client';
import type { DocumentOut } from '$lib/api/types';
import { UploadItem, UploadSession } from '$lib/upload/session.svelte';

import FileRow from './FileRow.svelte';

const api: DocumentsApi = {
	upload: () => new Promise(() => {}),
	get: () => new Promise(() => {}),
	setType: () => new Promise(() => {}),
	remove: async () => {}
};

const LONG_NAME =
	'Положение_о_департаменте_информационной_безопасности_и_рисков_редакция_2025_года.docx';

function stored(overrides: Partial<DocumentOut> = {}): DocumentOut {
	return {
		id: 7,
		file_name: 'Положение.docx',
		set: 'before',
		source_format: 'docx',
		file_size_bytes: 48213,
		content_sha256: '',
		uploaded_at: '2026-09-23T10:00:00Z',
		parse_status: 'parsed',
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
		node_count: 12,
		blocking_issues: 0,
		other_issues: 0,
		...overrides
	};
}

function item(
	name: string,
	status: UploadItem['status'],
	document: DocumentOut | null = null
): UploadItem {
	const upload = new UploadItem(new File(['x'], name), 'before');
	upload.status = status;
	upload.document = document;
	return upload;
}

function renderRow(upload: UploadItem, target?: HTMLElement) {
	const props = { item: upload, session: new UploadSession(api) };
	return target ? render(FileRow, { target, props }) : render(FileRow, props);
}

/** The file list of an upload zone on a 360 px phone screen; returns the zone and the list. */
async function phoneZone(): Promise<{ zone: HTMLElement; list: HTMLElement }> {
	await page.viewport(360, 800);
	const zone = document.createElement('div');
	zone.style.cssText =
		'display: grid; grid-template-columns: minmax(0, 1fr); width: 360px; padding: 16px; box-sizing: border-box';
	const list = document.createElement('ul');
	list.style.cssText = 'display: flex; flex-direction: column; gap: 8px';
	zone.append(list);
	document.body.append(zone);
	return { zone, list };
}

describe('FileRow', () => {
	it('says the type was not found and how to set it', async () => {
		const screen = await renderRow(item('Положение.docx', 'parsed', stored()));

		const input = screen.getByRole('combobox', { name: 'Тип документа' });
		await expect.element(input).toHaveValue('');
		await expect
			.element(input)
			.toHaveAccessibleDescription(
				'В документе тип не найден — выберите из списка или впишите свой.'
			);
	});

	it('tells how to correct a wrong type', async () => {
		const found = stored({ document_type: 'Положение о подразделении' });
		const screen = await renderRow(item('Положение.docx', 'parsed', found));

		const input = screen.getByRole('combobox', { name: 'Тип документа' });
		await expect.element(input).toHaveValue('Положение о подразделении');
		await expect
			.element(input)
			.toHaveAccessibleDescription(
				'Если тип неверный, выберите другой из списка или впишите свой.'
			);
	});

	it('shows a failed upload with its error and «Повторить»', async () => {
		const failed = item('Положение.docx', 'failed');
		failed.error = 'Сервер недоступен. Проверьте, что бэкенд запущен.';
		failed.retriable = true;
		const screen = await renderRow(failed);

		await expect.element(screen.getByText('Ошибка')).toBeVisible();
		await expect
			.element(screen.getByRole('alert'))
			.toHaveTextContent('Сервер недоступен. Проверьте, что бэкенд запущен.');
		await expect.element(screen.getByRole('button', { name: 'Повторить' })).toBeVisible();
	});

	it('offers no «Повторить» when repeating cannot help', async () => {
		const refused = item('Положение.doc', 'failed');
		refused.error = 'Формат .doc не поддерживается: сохраните файл как .docx.';
		const screen = await renderRow(refused);

		await expect.element(screen.getByRole('alert')).toBeVisible();
		await expect.element(screen.getByRole('button', { name: 'Повторить' })).not.toBeInTheDocument();
	});

	it('counts the problems of a document that needs review', async () => {
		const review = stored({ parse_status: 'needs_review', blocking_issues: 2, other_issues: 5 });
		const screen = await renderRow(item('Положение.docx', 'needs_review', review));

		await expect.element(screen.getByText('Требует проверки')).toBeVisible();
		await expect.element(screen.getByText('Блокирующих проблем: 2, прочих: 5')).toBeVisible();
	});

	it('keeps a long error and the type field within a phone screen', async () => {
		const { zone, list } = await phoneZone();
		const failed = item(LONG_NAME, 'failed');
		failed.error = `Не удалось прочитать ${LONG_NAME}`;
		await renderRow(failed, list);
		await renderRow(item(LONG_NAME, 'parsed', stored({ file_name: LONG_NAME })), list);

		await expect.element(page.getByRole('combobox', { name: 'Тип документа' })).toBeVisible();
		expect(zone.scrollWidth).toBeLessThanOrEqual(zone.clientWidth);
		zone.remove();
	});
});
