import { beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';

import './layout.css';
import { uploadSession } from '$lib/upload/current';
import { UploadItem } from '$lib/upload/session.svelte';

import Upload from './+page.svelte';

// The real session talks to the backend through $env; the page only needs one that stays idle.
vi.mock('$lib/upload/current', async () => {
	const { UploadSession } = await import('$lib/upload/session.svelte');
	const idle = () => new Promise<never>(() => {});
	return {
		uploadSession: new UploadSession({ upload: idle, get: idle, setType: idle, remove: idle })
	};
});

const LONG_NAME =
	'Положение_о_департаменте_информационной_безопасности_и_рисков_редакция_2025_года.docx';

function failed(name: string, set: 'before' | 'after'): UploadItem {
	const item = new UploadItem(new File(['x'], name), set);
	item.status = 'failed';
	item.error = 'Сервер недоступен. Проверьте, что бэкенд запущен.';
	return item;
}

beforeEach(() => {
	uploadSession.items = [];
});

describe('upload page', () => {
	it('introduces the analysis in the words of the prototype', async () => {
		const screen = await render(Upload);

		await expect
			.element(screen.getByRole('heading', { level: 1 }))
			.toHaveTextContent('Анализ реорганизации');
		await expect
			.element(
				screen.getByText(
					'Загрузите положение и штатное расписание до и после реорганизации. Агент покажет, что изменилось, и найдёт потерю функций, дублирование и конфликт интересов — со ссылкой на пункт документа.'
				)
			)
			.toBeVisible();
	});

	it('keeps «Начать анализ» disabled and says which documents are missing', async () => {
		const screen = await render(Upload);

		const start = screen.getByRole('button', { name: 'Начать анализ' });
		await expect.element(start).toBeDisabled();
		await expect.element(start).toHaveAccessibleDescription('Загрузите документы «До» и «После».');
	});

	it('wraps a long file name in the start hint on a phone screen', async () => {
		await page.viewport(360, 800);
		uploadSession.items = [failed(LONG_NAME, 'before'), failed('После.docx', 'after')];
		const frame = document.createElement('div');
		frame.style.cssText =
			'display: grid; width: 360px; padding-inline: 16px; box-sizing: border-box';
		document.body.append(frame);
		const screen = await render(Upload, { target: frame });

		await expect
			.element(screen.getByRole('button', { name: 'Начать анализ' }))
			.toHaveAccessibleDescription(
				`Файл «${LONG_NAME}» не загружен: повторите загрузку или удалите его.`
			);
		expect(frame.scrollWidth).toBeLessThanOrEqual(frame.clientWidth);
		frame.remove();
	});
});
