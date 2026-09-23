import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';

import '../../../routes/layout.css';

import StageCell from './StageCell.svelte';

/** The coloured dot in front of the state text. */
function dotOf(container: HTMLElement): HTMLElement {
	const dot = container.querySelector<HTMLElement>('[aria-hidden="true"]');
	if (dot === null) {
		throw new Error('StageCell rendered no dot');
	}
	return dot;
}

describe('StageCell', () => {
	it.each([
		['waiting', 'ждёт'],
		['running', 'в работе'],
		['done', 'готово'],
		['failed', 'ошибка']
	] as const)('spells out the %s state as «%s»', async (state, text) => {
		const screen = await render(StageCell, { state });

		await expect.element(screen.getByText(text)).toBeVisible();
	});

	it('spins the dot only while the stage is running', async () => {
		const running = await render(StageCell, { state: 'running' });
		const done = await render(StageCell, { state: 'done' });

		expect(getComputedStyle(dotOf(running.container)).animationName).toBe('spin');
		expect(getComputedStyle(dotOf(done.container)).animationName).toBe('none');
	});

	it('fills the dot of a done stage and of a failed one in different colours', async () => {
		const done = await render(StageCell, { state: 'done' });
		const failed = await render(StageCell, { state: 'failed' });
		const waiting = await render(StageCell, { state: 'waiting' });

		const fill = (container: HTMLElement) => getComputedStyle(dotOf(container)).backgroundColor;
		expect(fill(done.container)).not.toBe(fill(failed.container));
		expect(fill(waiting.container)).toBe('rgba(0, 0, 0, 0)');
	});
});
