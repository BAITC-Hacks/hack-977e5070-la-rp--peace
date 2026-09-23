/** A failed API call; `status` is 0 when the server could not be reached. */
export class ApiError extends Error {
	readonly status: number;

	constructor(message: string, status: number) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
	}

	/** Whether repeating the same request can succeed (network failure or server error). */
	get retriable(): boolean {
		return this.status === 0 || this.status >= 500;
	}
}

export const NETWORK_ERROR_MESSAGE = 'Сервер недоступен. Проверьте, что бэкенд запущен.';

/**
 * Extracts a human-readable message from a FastAPI error body.
 *
 * FastAPI answers `{"detail": "..."}` for errors raised by handlers and
 * `{"detail": [{"msg": "..."}, ...]}` for request validation errors.
 */
export function errorMessage(body: unknown, status: number): string {
	const detail =
		typeof body === 'object' && body !== null ? Reflect.get(body, 'detail') : undefined;
	if (typeof detail === 'string' && detail.length > 0) {
		return detail;
	}
	if (Array.isArray(detail)) {
		const messages = detail
			.map((item: unknown) =>
				typeof item === 'object' && item !== null ? Reflect.get(item, 'msg') : undefined
			)
			.filter((msg): msg is string => typeof msg === 'string');
		if (messages.length > 0) {
			return messages.join('; ');
		}
	}
	return `Ошибка сервера (HTTP ${status})`;
}
