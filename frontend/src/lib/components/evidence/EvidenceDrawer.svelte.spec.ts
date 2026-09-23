import { describe, expect, it, vi } from 'vitest';
import { userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';

import { ReviewState } from '$lib/result/review.svelte';
import type { Finding, Source } from '$lib/result/types';

import EvidenceDrawer from './EvidenceDrawer.svelte';

import '../../../routes/layout.css';

// Test data after finding C-010 of docs/spec/visual_compare.html.
const before: Source = {
	doc: 'before',
	block: 'Положение СВА',
	node_id: 17,
	clause: 'п. 2.5',
	quote: 'проводит аудит системы защиты информации',
	item: 'f_audit'
};

const after: Source = {
	doc: 'after',
	block: 'Положение ДИБиР',
	node_id: 58,
	clause: 'п. 2.8',
	quote: 'проводит аудит системы защиты информации',
	item: 'g_audit'
};

const conflict: Finding = {
	id: 'C-010',
	type: 'conflict',
	block: 'ИБ и режим',
	title: 'Конфликт интересов',
	desc: 'ДИБиР внедряет меры защиты и сам их проверяет',
	from: ['f_audit'],
	to: ['g_audit'],
	also: ['g_prot'],
	evidence: {
		conclusion: 'После реорганизации ДИБиР одновременно реализует меры защиты и проводит их аудит.',
		method: 'Правило несовместимости «исполняет — контролирует».',
		steps: [
			{ kind: 'fact', text: 'До реорганизации аудит ИБ проводила СВА.', sources: [before] },
			{ kind: 'fact', text: 'После реорганизации аудит закреплён за ДИБиР.', sources: [after] },
			{
				kind: 'inference',
				text: 'Исполнение и контроль оказались у одного субъекта.',
				sources: []
			}
		],
		checked: {
			scope: 'Все 23 пункта документа «после»',
			threshold: 0.75,
			candidates: [{ label: 'Пропускной режим', clause: 'п. 2.3', score: 0.38, item: 'g_pass' }]
		},
		npa: 'НПА не загружены: вывод сделан только по документам.',
		confidence: 'high',
		confidence_note: 'Факты подтверждены цитатами; несовместимость — рассуждение агента.'
	},
	review: null
};

async function open(finding: Finding = conflict) {
	const review = new ReviewState([finding]);
	const onclose = vi.fn();
	const onquote = vi.fn();
	const screen = await render(EvidenceDrawer, { finding, review, onclose, onquote });
	return { screen, review, onclose, onquote };
}

describe('EvidenceDrawer', () => {
	it('opens as a modal dialog when given a finding and closes when it is taken away', async () => {
		const review = new ReviewState([conflict]);
		const screen = await render(EvidenceDrawer, {
			finding: null,
			review,
			onclose: vi.fn(),
			onquote: vi.fn()
		});
		const dialog = screen.container.querySelector('dialog') as HTMLDialogElement;
		expect(dialog.open).toBe(false);

		await screen.rerender({ finding: conflict });

		await expect.element(screen.getByRole('dialog')).toBeVisible();
		expect(dialog.matches(':modal')).toBe(true);
		await expect
			.element(screen.getByRole('heading', { level: 2 }))
			.toHaveTextContent(conflict.evidence.conclusion);

		await screen.rerender({ finding: null });

		expect(dialog.open).toBe(false);
	});

	it('shows the evidence sections in order, ending with the disclaimer', async () => {
		const { screen } = await open();

		const headings = [...screen.container.querySelectorAll('dialog h3')].map(
			(heading) => heading.textContent
		);
		expect(headings).toEqual([
			'Как получен вывод',
			'Цепочка доказательств',
			'Что проверено',
			'Нормативная база',
			'Уверенность',
			'Проверка сотрудником'
		]);
		await expect.element(screen.getByText('Конфликт интересов · C-010')).toBeVisible();
		await expect.element(screen.getByText('Пропускной режим')).toBeVisible();
		await expect.element(screen.getByText('0,38')).toBeVisible();
		await expect.element(screen.getByText(/Порог совпадения: 0,75/)).toBeVisible();
		await expect.element(screen.getByText('высокая')).toBeVisible();
		const last = screen.container.querySelector('dialog > div > :last-child');
		expect(last?.textContent).toBe(
			'Вывод носит рекомендательный характер и требует проверки ответственным сотрудником.'
		);
	});

	it('labels the agent reasoning and leaves facts unlabelled', async () => {
		const { screen } = await open();

		const steps = screen.container.querySelectorAll('dialog ol > li');
		expect(steps).toHaveLength(3);
		expect(steps[0].textContent).not.toContain('рассуждение агента');
		expect(steps[2].textContent).toContain('рассуждение агента');
	});

	it('skips the checks and the regulatory basis when the finding has none', async () => {
		const { screen } = await open({
			...conflict,
			evidence: { ...conflict.evidence, checked: null, npa: undefined }
		});

		await expect.element(screen.getByRole('heading', { name: 'Уверенность' })).toBeVisible();
		expect(screen.container.textContent).not.toContain('Что проверено');
		expect(screen.container.textContent).not.toContain('Нормативная база');
	});

	it('hands a clicked quote to onquote', async () => {
		const { screen, onquote } = await open();

		await screen
			.getByRole('button', { name: /Документ «после» · Положение ДИБиР · п. 2.8/ })
			.click();

		expect(onquote).toHaveBeenCalledWith(after);
	});

	it('confirms, clears on a second click and rejects', async () => {
		const { screen, review } = await open();
		const confirm = screen.getByRole('button', { name: '✓ Подтвердить' });
		const reject = screen.getByRole('button', { name: '✕ Отклонить' });

		await confirm.click();
		await expect.element(confirm).toHaveAttribute('aria-pressed', 'true');
		expect(review.verdictOf('C-010')).toBe('ok');

		await confirm.click();
		await expect.element(confirm).toHaveAttribute('aria-pressed', 'false');
		expect(review.verdictOf('C-010')).toBeNull();

		await reject.click();
		await expect.element(reject).toHaveAttribute('aria-pressed', 'true');
		await expect.element(confirm).toHaveAttribute('aria-pressed', 'false');
		expect(review.verdictOf('C-010')).toBe('no');
	});

	it('closes on Escape', async () => {
		const { screen, onclose } = await open();
		await expect.element(screen.getByRole('dialog')).toBeVisible();

		await userEvent.keyboard('{Escape}');

		await vi.waitFor(() => expect(onclose).toHaveBeenCalled());
	});

	it('closes with the × button', async () => {
		const { screen, onclose } = await open();

		await screen.getByRole('button', { name: 'Закрыть' }).click();

		await vi.waitFor(() => expect(onclose).toHaveBeenCalled());
		expect((screen.container.querySelector('dialog') as HTMLDialogElement).open).toBe(false);
	});
});
