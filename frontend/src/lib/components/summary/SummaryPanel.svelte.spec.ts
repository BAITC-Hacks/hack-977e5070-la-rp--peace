import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';

import { ReviewState } from '$lib/result/review.svelte';
import type { Finding, JobResult } from '$lib/result/types';

import SummaryPanel from './SummaryPanel.svelte';

import '../../../routes/layout.css';

function finding(
	id: string,
	type: Finding['type'],
	quotes: string[],
	review: Finding['review'] = null
): Finding {
	return {
		id,
		type,
		block: 'ИБ и режим',
		title: id,
		from: [],
		to: [],
		evidence: {
			conclusion: `Вывод ${id}`,
			method: 'Метод',
			steps: [
				{
					kind: 'fact',
					text: 'Факт',
					sources: quotes.map((quote) => ({
						doc: 'after',
						block: 'Положение ДИБиР',
						node_id: 3,
						clause: 'п. 2.8',
						quote,
						item: null
					}))
				}
			],
			confidence: 'high'
		},
		review
	};
}

function testResult(): JobResult {
	const findings = [
		finding('C-010', 'conflict', ['проводит аудит системы защиты информации'], 'ok'),
		finding('C-011', 'loss', ['организует мобилизационную подготовку']),
		finding('C-012', 'kept', ['разрабатывает ИТ-стратегию организации']),
		// No quote: hidden (I1), not counted, not a link.
		finding('C-099', 'duplication', [])
	];
	return {
		job_id: 'job-1',
		summary: { changed_blocks: ['Структура', 'ИБ и режим'], counts: { loss: 1 } },
		conclusion:
			'ДИБиР проверяет сам себя (C-010). Мобподготовка не закреплена (C-011). Дублирование C-099 не подтверждено.',
		blocks: [],
		findings: Object.fromEntries(findings.map((item) => [item.id, item]))
	};
}

async function show() {
	const result = testResult();
	const review = new ReviewState(
		Object.values(result.findings).filter((item) => item.id !== 'C-099')
	);
	const onopen = vi.fn();
	const screen = await render(SummaryPanel, { result, review, onopen });
	return { screen, review, onopen };
}

describe('SummaryPanel', () => {
	it('turns mentions of shown findings in the conclusion into buttons', async () => {
		const { screen, onopen } = await show();

		await screen.getByRole('button', { name: 'C-011' }).click();

		expect(onopen).toHaveBeenCalledWith('C-011');
		await expect.element(screen.getByRole('button', { name: 'C-010' })).toBeVisible();
		expect(screen.getByRole('button', { name: 'C-099' }).elements()).toHaveLength(0);
		await expect.element(screen.getByText(/Дублирование C-099 не подтверждено/)).toBeVisible();
	});

	it('lists the changed blocks', async () => {
		const { screen } = await show();

		await expect.element(screen.getByText('Структура · ИБ и режим')).toBeVisible();
	});

	it('counts shown findings by type', async () => {
		const { screen } = await show();

		const chips = screen.getByRole('list', { name: 'Находки по типам' }).getByRole('listitem');
		expect(chips.elements().map((chip) => chip.textContent?.trim())).toEqual([
			'Сохранено: 1',
			'Потеря функции: 1',
			'Конфликт интересов: 1'
		]);
	});

	it('shows how many findings the employee has checked', async () => {
		const { screen, review } = await show();
		await expect.element(screen.getByText('Проверено сотрудником: 1 из 3')).toBeVisible();

		review.toggle('C-011', 'no');

		await expect.element(screen.getByText('Проверено сотрудником: 2 из 3')).toBeVisible();
	});

	it('prints the page as PDF and keeps the button off the paper', async () => {
		const print = vi.spyOn(window, 'print').mockImplementation(() => {});
		const { screen } = await show();

		const button = screen.getByRole('button', { name: 'Скачать PDF' });
		await expect.element(button).toHaveAttribute('data-print', 'hide');
		await button.click();

		expect(print).toHaveBeenCalledOnce();
		print.mockRestore();
	});
});
