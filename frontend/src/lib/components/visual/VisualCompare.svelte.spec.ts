import { beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';

import EvidenceDrawer from '$lib/components/evidence/EvidenceDrawer.svelte';
import { ReviewState } from '$lib/result/review.svelte';
import type { Finding, JobResult, Source } from '$lib/result/types';

import VisualCompare from './VisualCompare.svelte';

// The app styles: the geometry checks need the real grid.
import '../../../routes/layout.css';

// Test data after the «ИБ и режим» block of docs/spec/visual_compare.html.
function source(doc: Source['doc'], clause: string, quote: string, item: string): Source {
	return { doc, block: 'Положение', node_id: 1, clause, quote, item };
}

function finding(
	id: string,
	type: Finding['type'],
	title: string,
	links: Pick<Finding, 'from' | 'to' | 'also'>,
	sources: Source[]
): Finding {
	return {
		id,
		type,
		block: 'ИБ и режим',
		title,
		desc: `Описание ${id}`,
		...links,
		evidence: {
			conclusion: `Вывод ${id}`,
			method: 'Метод',
			steps: [{ kind: 'fact', text: 'Факт', sources }],
			confidence: 'high'
		},
		review: null
	};
}

function testResult(): JobResult {
	const findings = [
		finding('C-007', 'kept', 'Сохранено', { from: ['f_prot'], to: ['g_prot'] }, [
			source('before', 'п. 2.1', 'обеспечивает реализацию мер по защите информации', 'f_prot')
		]),
		finding(
			'C-010',
			'conflict',
			'Конфликт интересов',
			{ from: ['f_audit'], to: ['g_audit'], also: ['g_prot'] },
			[
				source('before', 'п. 2.5', 'проводит аудит системы защиты информации', 'f_audit'),
				source('after', 'п. 2.8', 'проводит аудит системы защиты информации', 'g_audit')
			]
		),
		finding('C-011', 'loss', 'Потеря функции', { from: ['f_mob'], to: [] }, [
			source('before', 'п. 3.7', 'организует мобилизационную подготовку', 'f_mob')
		]),
		// No quote: must not be shown (I1).
		finding('C-099', 'conflict', 'Конфликт интересов', { from: ['f_mob'], to: ['g_prot'] }, [])
	];
	return {
		job_id: 'job-1',
		summary: { changed_blocks: ['ИБ и режим'], counts: {} },
		conclusion: '',
		blocks: [
			{
				title: 'ИБ и режим',
				before: [
					{ id: 'f_prot', label: 'Меры защиты информации — ДИБ, п. 2.1', clause_id: 'b:2.1' },
					{ id: 'f_audit', label: 'Аудит ИБ — СВА, п. 2.5', clause_id: 'b:2.5' },
					{
						id: 'f_mob',
						label: 'Мобподготовка — Отдел режима, п. 3.7',
						status: 'loss',
						clause_id: 'b:3.7'
					}
				],
				after: [
					{
						id: 'g_prot',
						label: 'Меры защиты информации — ДИБиР, п. 2.2',
						status: 'kept',
						clause_id: 'a:2.2'
					},
					{ id: 'g_audit', label: 'Аудит ИБ — ДИБиР, п. 2.8', status: 'moved', clause_id: 'a:2.8' }
				],
				changes: ['C-007', 'C-010', 'C-011', 'C-099']
			}
		],
		findings: Object.fromEntries(findings.map((item) => [item.id, item]))
	};
}

function setup() {
	const result = testResult();
	const review = new ReviewState(Object.values(result.findings));
	const onopen = vi.fn();
	return { result, review, onopen };
}

const arrow = (container: HTMLElement, key: string) =>
	container.querySelector<SVGPathElement>(`path[data-arrow="${key}"]`);

const itemRow = (container: HTMLElement, id: string) =>
	page.elementLocator(container.querySelector(`[data-item="${id}"]`) as HTMLElement);

beforeEach(async () => {
	await page.viewport(1280, 900);
});

describe('VisualCompare', () => {
	it('renders the columns, the sourced cards and their status badges', async () => {
		const screen = await render(VisualCompare, setup());

		await expect.element(screen.getByRole('heading', { name: 'ИБ и режим' })).toBeVisible();
		await expect.element(screen.getByRole('list', { name: 'Документ «до»' })).toBeVisible();
		await expect.element(screen.getByRole('list', { name: 'Документ «после»' })).toBeVisible();
		await expect
			.element(screen.getByRole('button', { name: /C-010 · источников: 2/ }))
			.toBeVisible();
		await expect.element(screen.getByRole('button', { name: /^Сохранено/ })).toBeVisible();
		await expect.element(screen.getByText('потеряна')).toBeVisible();
		await expect.element(screen.getByText('перенесено')).toBeVisible();
		expect(screen.container.textContent).not.toContain('C-099');
	});

	it('draws from, to, dashed also and the loss mark between the boxes', async () => {
		const { container } = await render(VisualCompare, setup());

		await expect.poll(() => container.querySelectorAll('path[data-arrow]').length).toBe(7);
		expect(arrow(container, 'C-010:from:f_audit')?.getAttribute('marker-end')).toBeNull();
		expect(arrow(container, 'C-010:to:g_audit')?.getAttribute('marker-end')).toMatch(/^url\(#/);
		expect(arrow(container, 'C-010:also:g_prot')?.getAttribute('stroke-dasharray')).toBe('5 4');
		expect(arrow(container, 'C-011:loss')?.getAttribute('stroke-dasharray')).toBe('3 3');
		expect(container.querySelector('svg text')?.textContent?.trim()).toBe('∅ не закреплено');
		expect(container.textContent).not.toContain('C-099');

		// The arrow into «после» ends at the middle of its item, just before the column.
		const path = arrow(container, 'C-010:to:g_audit') as SVGPathElement;
		const end = path.getPointAtLength(path.getTotalLength());
		const svg = (path.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
		const item = (
			container.querySelector('[data-item="g_audit"]') as HTMLElement
		).getBoundingClientRect();
		const column = (
			container.querySelector('[data-column="after"]') as HTMLElement
		).getBoundingClientRect();
		expect(end.y).toBeCloseTo(item.top + item.height / 2 - svg.top, 0);
		expect(end.x).toBeCloseTo(column.left - 2 - svg.left, 0);
	});

	it('lights the whole link of a hovered card and dims the rest', async () => {
		const screen = await render(VisualCompare, setup());
		const conflict = screen.getByRole('button', { name: /C-010/ });
		const loss = screen.getByRole('button', { name: /C-011/ });

		await conflict.hover();

		await expect.element(loss).toHaveClass('opacity-35');
		await expect.element(conflict).not.toHaveClass('opacity-35');
		await expect.element(itemRow(screen.container, 'g_prot')).toHaveClass('bg-neutral-soft');
		await expect.element(itemRow(screen.container, 'f_mob')).toHaveClass('opacity-35');
		expect(arrow(screen.container, 'C-011:loss')?.classList).toContain('opacity-10');
		expect(arrow(screen.container, 'C-010:also:g_prot')?.classList).not.toContain('opacity-10');

		await conflict.unhover();

		await expect.element(loss).not.toHaveClass('opacity-35');
	});

	it('lights every finding of a hovered item', async () => {
		const screen = await render(VisualCompare, setup());

		await itemRow(screen.container, 'g_prot').hover();

		await expect
			.element(screen.getByRole('button', { name: /^Сохранено/ }))
			.not.toHaveClass('opacity-35');
		await expect
			.element(screen.getByRole('button', { name: /C-010/ }))
			.not.toHaveClass('opacity-35');
		await expect.element(screen.getByRole('button', { name: /C-011/ })).toHaveClass('opacity-35');
	});

	it('lights the link of a card focused from the keyboard', async () => {
		const screen = await render(VisualCompare, setup());

		(screen.getByRole('button', { name: /C-011/ }).element() as HTMLButtonElement).focus();

		await expect.element(screen.getByRole('button', { name: /C-010/ })).toHaveClass('opacity-35');
		await expect.element(itemRow(screen.container, 'f_mob')).toHaveClass('bg-neutral-soft');
	});

	it('opens the evidence of a clicked card, where a verdict marks the card', async () => {
		const { result, review, onopen } = setup();
		const visual = await render(VisualCompare, { result, review, onopen });
		const drawer = await render(EvidenceDrawer, {
			finding: null,
			review,
			onclose: vi.fn(),
			onquote: vi.fn()
		});

		await visual.getByRole('button', { name: /C-010/ }).click();
		expect(onopen).toHaveBeenCalledWith('C-010');
		await drawer.rerender({ finding: result.findings['C-010'] });
		await expect.element(drawer.getByRole('dialog')).toBeVisible();
		await drawer.getByRole('button', { name: '✓ Подтвердить' }).click();
		await drawer.rerender({ finding: null });

		await expect
			.element(visual.getByRole('button', { name: /C-010/ }))
			.toHaveTextContent('✓ подтверждено');
		expect(review.reviewed).toBe(1);
	});
});
