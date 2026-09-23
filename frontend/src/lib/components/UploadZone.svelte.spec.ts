import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';

import '../../routes/layout.css';
import type { DocumentsApi } from '$lib/api/client';
import { DOC_SETS } from '$lib/documents';
import { UploadSession } from '$lib/upload/session.svelte';

import UploadZone from './UploadZone.svelte';

/** Uploads never finish, so every accepted file stays on screen as «Загрузка 0%». */
const api: DocumentsApi = {
	upload: () => new Promise(() => {}),
	get: () => new Promise(() => {}),
	setType: () => new Promise(() => {}),
	remove: async () => {}
};

const BEFORE = DOC_SETS.find((info) => info.set === 'before')!;
const REGULATORY = DOC_SETS.find((info) => info.set === 'regulatory')!;
const LONG_NAME =
	'Положение_о_департаменте_информационной_безопасности_и_рисков_редакция_2025_года.txt';

const file = (name: string) => new File(['x'], name);

function transfer(files: File[]): DataTransfer {
	const data = new DataTransfer();
	for (const item of files) {
		data.items.add(item);
	}
	return data;
}

/** Picks files through the zone's hidden file input, as the file dialog would. */
function pick(container: HTMLElement, files: File[]) {
	const input = container.querySelector<HTMLInputElement>('input[type="file"]');
	if (input === null) {
		throw new Error('the zone shows no file input');
	}
	input.files = transfer(files).files;
	input.dispatchEvent(new Event('change', { bubbles: true }));
}

function drop(container: HTMLElement, files: File[]) {
	const zone = container.querySelector('[role="region"]');
	zone?.dispatchEvent(
		new DragEvent('drop', { dataTransfer: transfer(files), bubbles: true, cancelable: true })
	);
}

/** A 360 px phone screen: the page column is a grid, so it grows with unbreakable content. */
async function phoneFrame(): Promise<HTMLElement> {
	await page.viewport(360, 800);
	const frame = document.createElement('div');
	frame.style.cssText = 'display: grid; width: 360px; padding-inline: 16px; box-sizing: border-box';
	document.body.append(frame);
	return frame;
}

afterEach(() => {
	delete document.documentElement.dataset.theme;
});

describe('UploadZone', () => {
	it('shows the format hint of the prototype in a required zone', async () => {
		const screen = await render(UploadZone, { session: new UploadSession(api), info: BEFORE });

		await expect.element(screen.getByText('Обязательно')).toBeVisible();
		await expect.element(screen.getByRole('heading', { name: 'Документ «До»' })).toBeVisible();
		await expect
			.element(screen.getByText('Word, PDF или Excel. Штатное расписание — внутри документа.'))
			.toBeVisible();
	});

	it('invites to drop files into an empty optional zone and names the formats', async () => {
		const screen = await render(UploadZone, {
			session: new UploadSession(api),
			info: REGULATORY
		});

		await expect.element(screen.getByText(/Перетащите файлы сюда или/)).toBeVisible();
		await expect
			.element(screen.getByText('Word, PDF или Excel: .docx, .doc, .pdf, .xlsx, .xls'))
			.toBeVisible();
		await expect.element(screen.getByRole('listitem')).not.toBeInTheDocument();
	});

	it('refuses an unsupported format and says which formats are accepted', async () => {
		const session = new UploadSession(api);
		const screen = await render(UploadZone, { session, info: BEFORE });

		pick(screen.container, [file('scan.jpg')]);

		await expect
			.element(screen.getByRole('alert'))
			.toHaveTextContent(
				'Формат не поддерживается: scan.jpg. Допустимы .docx, .doc, .pdf, .xlsx, .xls.'
			);
		expect(session.items).toHaveLength(0);
	});

	it('asks for one file when several are dropped on a required zone', async () => {
		const session = new UploadSession(api);
		const screen = await render(UploadZone, { session, info: BEFORE });

		drop(screen.container, [file('a.docx'), file('b.docx')]);

		await expect
			.element(screen.getByRole('alert'))
			.toHaveTextContent('Нужен один файл — перетащите только его.');
		expect(session.items).toHaveLength(0);
	});

	it('refuses a second file on a filled required zone', async () => {
		const session = new UploadSession(api);
		const screen = await render(UploadZone, { session, info: BEFORE });
		pick(screen.container, [file('a.docx')]);
		await expect.element(screen.getByText('a.docx')).toBeVisible();

		drop(screen.container, [file('b.docx')]);

		await expect
			.element(screen.getByRole('alert'))
			.toHaveTextContent('Файл уже загружен. Удалите его, чтобы выбрать другой.');
		expect(session.items.map((item) => item.file.name)).toEqual(['a.docx']);
	});

	it('wraps the name of a refused file instead of widening a phone screen', async () => {
		const frame = await phoneFrame();
		const screen = await render(UploadZone, {
			target: frame,
			props: { session: new UploadSession(api), info: BEFORE }
		});

		pick(screen.container, [file(LONG_NAME)]);

		await expect.element(screen.getByRole('alert')).toHaveTextContent(LONG_NAME);
		expect(frame.scrollWidth).toBeLessThanOrEqual(frame.clientWidth);
		frame.remove();
	});

	it('shows the file error in the dark theme colour', async () => {
		document.documentElement.dataset.theme = 'dark';
		const screen = await render(UploadZone, { session: new UploadSession(api), info: BEFORE });

		pick(screen.container, [file('scan.jpg')]);

		const alert = screen.getByRole('alert');
		await expect.element(alert).toBeVisible();
		// --bad of the dark theme in docs/spec/prototype.html.
		expect(getComputedStyle(alert.element()).color).toBe('rgb(242, 163, 156)');
	});
});
