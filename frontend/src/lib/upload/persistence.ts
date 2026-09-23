import type { DocSet } from '$lib/api/types';

export const UPLOAD_SESSION_KEY = 'upload-session:v1';

/** Only references to this tab's uploaded documents, never their contents or cached results. */
export interface SavedUpload {
	id: number;
	set: DocSet;
	name: string;
	size: number;
}

export type SessionStorage = Pick<Storage, 'getItem' | 'setItem'>;

const SETS: readonly string[] = ['before', 'after', 'regulatory', 'benchmark'];

function isSavedUpload(value: unknown): value is SavedUpload {
	if (typeof value !== 'object' || value === null) return false;
	const item = value as Partial<SavedUpload>;
	return (
		typeof item.id === 'number' &&
		Number.isSafeInteger(item.id) &&
		item.id > 0 &&
		typeof item.set === 'string' &&
		SETS.includes(item.set) &&
		typeof item.name === 'string' &&
		item.name.length > 0 &&
		typeof item.size === 'number' &&
		Number.isSafeInteger(item.size) &&
		item.size >= 0
	);
}

/** Malformed or unsupported snapshots are ignored in full; they cannot trigger API requests. */
export function readSavedUploads(value: string | null): SavedUpload[] {
	if (value === null) return [];
	let snapshot: unknown;
	try {
		snapshot = JSON.parse(value);
	} catch {
		return [];
	}
	if (typeof snapshot !== 'object' || snapshot === null) return [];
	const { version, items } = snapshot as { version?: unknown; items?: unknown };
	if (version !== 1 || !Array.isArray(items) || !items.every(isSavedUpload)) return [];
	return items.filter((item, index) => items.findIndex((other) => other.id === item.id) === index);
}
