/** Extensions the upload zones take (tech task §5: Word, PDF, Excel). The backend rejects .doc/.xls with advice. */
export const ACCEPTED_EXTENSIONS = ['.docx', '.doc', '.pdf', '.xlsx', '.xls'] as const;

/** Value for the file input's `accept` attribute. */
export const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.join(',');

/** Lower-cased extension including the dot, or '' when the name has none. */
export function extensionOf(filename: string): string {
	const dot = filename.lastIndexOf('.');
	return dot <= 0 ? '' : filename.slice(dot).toLowerCase();
}

/** Whether a file with this name may be uploaded. */
export function isAccepted(filename: string): boolean {
	return (ACCEPTED_EXTENSIONS as readonly string[]).includes(extensionOf(filename));
}

const SIZE_UNITS = ['КБ', 'МБ', 'ГБ'] as const;

/** Human-readable file size in Russian units, e.g. «1,5 МБ». */
export function formatSize(bytes: number): string {
	if (bytes < 1024) {
		return `${bytes} Б`;
	}
	let value = bytes / 1024;
	let unit = 0;
	while (value >= 1024 && unit < SIZE_UNITS.length - 1) {
		value /= 1024;
		unit += 1;
	}
	const digits = value < 10 ? 1 : 0;
	return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits }).format(value)} ${SIZE_UNITS[unit]}`;
}
