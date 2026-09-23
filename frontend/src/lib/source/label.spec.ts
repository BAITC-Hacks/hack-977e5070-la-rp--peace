import { describe, expect, it } from 'vitest';

import { sourceLabel } from './label';

describe('sourceLabel', () => {
	it('joins the side and the anchor', () => {
		expect(sourceLabel('before', 'п. 3.4')).toBe('До · п. 3.4');
		expect(sourceLabel('after', 'п. 3.4 «а»')).toBe('После · п. 3.4 «а»');
	});

	it('leaves out an unknown part', () => {
		expect(sourceLabel(null, 'п. 2.5')).toBe('п. 2.5');
		expect(sourceLabel('regulatory', '  ')).toBe('НПА');
		expect(sourceLabel(null, '')).toBe('Источник');
	});
});
