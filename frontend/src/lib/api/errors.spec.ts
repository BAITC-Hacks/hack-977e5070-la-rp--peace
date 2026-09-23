import { describe, expect, it } from 'vitest';

import { ApiError, errorMessage } from './errors';

describe('errorMessage', () => {
	it('uses a string detail as is', () => {
		const body = { detail: 'Формат .doc не поддерживается: пересохраните как .docx' };
		expect(errorMessage(body, 415)).toBe(body.detail);
	});

	it('joins the messages of a validation error', () => {
		const body = { detail: [{ msg: 'Field required' }, { msg: 'Input should be a valid enum' }] };
		expect(errorMessage(body, 422)).toBe('Field required; Input should be a valid enum');
	});

	it('falls back to the status code for bodies without a detail', () => {
		expect(errorMessage(null, 502)).toBe('Ошибка сервера (HTTP 502)');
		expect(errorMessage({ detail: [] }, 500)).toBe('Ошибка сервера (HTTP 500)');
		expect(errorMessage('Internal Server Error', 500)).toBe('Ошибка сервера (HTTP 500)');
	});
});

describe('ApiError.retriable', () => {
	it('is true for network failures and server errors only', () => {
		expect(new ApiError('', 0).retriable).toBe(true);
		expect(new ApiError('', 503).retriable).toBe(true);
		expect(new ApiError('', 413).retriable).toBe(false);
		expect(new ApiError('', 415).retriable).toBe(false);
	});
});
