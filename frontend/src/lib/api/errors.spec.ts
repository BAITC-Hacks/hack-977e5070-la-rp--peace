import { describe, expect, it } from 'vitest';

import { ApiError, errorMessage } from './errors';

describe('errorMessage', () => {
	// Messages as the upload endpoint raises them (src/la_rp_peace/api/documents.py).
	it.each([
		[503, 'Разбор недоступен: не заданы OPENAI_API_KEY и OPENAI_MODEL'],
		[413, 'Файл больше 20 МБ'],
		[415, 'Формат .doc не поддерживается: пересохраните файл как .docx']
	])('uses the string detail of HTTP %i as is', (status, detail) => {
		expect(errorMessage({ detail }, status)).toBe(detail);
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
