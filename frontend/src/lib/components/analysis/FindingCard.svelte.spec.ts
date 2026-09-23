import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';

import type { Finding } from '$lib/result/types';

import FindingCard from './FindingCard.svelte';

import '../../../routes/layout.css';

// Test data after finding C-011 of docs/spec/visual_compare.html.
const loss: Finding = {
	id: 'C-011',
	type: 'loss',
	block: 'ИБ и режим',
	title: 'Мобилизационная подготовка',
	desc: 'Мобподготовка не закреплена ни за кем',
	from: ['f_mob'],
	to: [],
	evidence: {
		conclusion: 'Функция мобилизационной подготовки не закреплена ни за одним подразделением.',
		method: 'Сопоставление функций «до» и «после».',
		steps: [
			{
				kind: 'fact',
				text: 'До реорганизации функцию выполнял Отдел режима.',
				sources: [
					{
						doc: 'before',
						block: 'Положение Отдела режима',
						node_id: 17,
						clause: 'п. 3.7',
						quote: 'организует мобилизационную подготовку и мобилизацию',
						item: 'f_mob'
					}
				]
			}
		],
		confidence: 'low',
		confidence_note: null
	},
	review: null
};

describe('FindingCard', () => {
	it('shows a title that says more than the type, and no basis when there is none', async () => {
		const screen = render(FindingCard, { finding: loss, verdict: null, onopen: vi.fn() });

		const card = screen.getByRole('button');
		await expect.element(card).toHaveTextContent(/^Потеря функции C-011 · ИБ и режим/);
		await expect.element(screen.getByText('Мобилизационная подготовка')).toBeVisible();
		await expect.element(card).toHaveTextContent(/Уверенность:\s*низкая$/);
		expect(card.element().textContent).not.toContain('подтверждено');
	});

	it('does not repeat the type label as the title', async () => {
		const screen = render(FindingCard, {
			finding: { ...loss, title: 'Потеря функции' },
			verdict: null,
			onopen: vi.fn()
		});

		await expect.element(screen.getByRole('button')).toBeVisible();
		expect(screen.getByText('Потеря функции', { exact: true }).elements()).toHaveLength(1);
	});

	it('shows the rejection and opens the finding on click', async () => {
		const onopen = vi.fn();
		const screen = render(FindingCard, { finding: loss, verdict: 'no', onopen });

		await expect.element(screen.getByText('✕ отклонено')).toBeVisible();
		await screen.getByRole('button').click();

		expect(onopen).toHaveBeenCalledWith('C-011');
	});
});
