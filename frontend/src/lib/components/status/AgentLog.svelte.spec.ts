import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';

import type { AgentLogEntry } from '$lib/api/analyses';
import { logTime } from '$lib/status/analysis-stages';

import '../../../routes/layout.css';

import AgentLog from './AgentLog.svelte';

/** `count` steps a second apart, numbered from `from`. */
function steps(count: number, from = 1): AgentLogEntry[] {
	return Array.from({ length: count }, (_, index) => ({
		at: new Date(Date.UTC(2026, 8, 23, 10, 0, from + index)).toISOString(),
		message: `Шаг ${from + index}`
	}));
}

function listOf(container: HTMLElement): HTMLElement {
	const list = container.querySelector('ol');
	if (list === null) {
		throw new Error('AgentLog rendered no list');
	}
	return list;
}

/** Whether the newest step is scrolled into view. */
const atBottom = (list: HTMLElement) => list.scrollHeight - list.scrollTop - list.clientHeight < 2;

describe('AgentLog', () => {
	it('lists every step with its time, oldest first', async () => {
		const entries = steps(2);
		const screen = await render(AgentLog, { entries });

		const items = screen.getByRole('listitem').elements();
		expect(items.map((item) => item.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
			`${logTime(entries[0].at)} Шаг 1`,
			`${logTime(entries[1].at)} Шаг 2`
		]);
		expect(items[0].querySelector('time')?.getAttribute('datetime')).toBe(entries[0].at);
	});

	it('says so while the agent has not reported anything', async () => {
		const screen = await render(AgentLog, { entries: [] });

		await expect.element(screen.getByText('Агент ещё не сообщил о шагах.')).toBeVisible();
	});

	it('keeps the newest step in view as steps arrive', async () => {
		const screen = await render(AgentLog, { entries: steps(40) });
		const list = listOf(screen.container);
		expect(list.scrollHeight).toBeGreaterThan(list.clientHeight);
		expect(atBottom(list)).toBe(true);

		await screen.rerender({ entries: steps(60) });

		expect(atBottom(list)).toBe(true);
	});

	it('stays where the reader is while paused, and catches up on resume', async () => {
		const screen = await render(AgentLog, { entries: steps(40) });
		const list = listOf(screen.container);

		await screen.getByRole('button', { name: 'Пауза' }).click();
		list.scrollTop = 0;
		await screen.rerender({ entries: steps(60) });
		expect(list.scrollTop).toBe(0);

		await screen.getByRole('button', { name: 'Продолжить прокрутку' }).click();
		await expect.poll(() => atBottom(list)).toBe(true);
	});
});
