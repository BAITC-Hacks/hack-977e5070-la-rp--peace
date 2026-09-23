import type { Verdict } from '$lib/result/types';

/**
 * The employee's marks on one analysis, by finding id. `null` records that the employee cleared a
 * verdict the result itself carries, so that the clearing survives a reload too.
 */
export type SavedVerdicts = Record<string, Verdict | null>;

/** Where the marks of an analysis are kept between visits. Implementations never throw. */
export interface ReviewStorage {
	/** The saved marks of the job; nothing saved or unreadable gives an empty record. */
	load(jobId: string): SavedVerdicts;
	/** Replaces the saved marks of the job; an empty record removes them. */
	save(jobId: string, verdicts: SavedVerdicts): void;
}

/** The part of `Storage` the marks use, so tests can pass a plain object. */
export type WebStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export function reviewStorageKey(jobId: string): string {
	return `larp:review:${jobId}`;
}

function isSavedValue(value: unknown): value is Verdict | null {
	return value === 'ok' || value === 'no' || value === null;
}

/** Keeps only the entries a `SavedVerdicts` may hold; anything else in storage is ignored. */
function parseSaved(raw: string | null): SavedVerdicts {
	if (raw === null) {
		return {};
	}
	const value: unknown = JSON.parse(raw);
	if (typeof value !== 'object' || value === null || Array.isArray(value)) {
		return {};
	}
	return Object.fromEntries(Object.entries(value).filter(([, verdict]) => isSavedValue(verdict)));
}

/**
 * Marks kept in a web storage. `storage` is asked for on every read and write: getting it throws
 * where the browser blocks site data, and then the marks just are not remembered.
 */
export function webReviewStorage(storage: () => WebStorage): ReviewStorage {
	return {
		load(jobId) {
			try {
				return parseSaved(storage().getItem(reviewStorageKey(jobId)));
			} catch {
				return {};
			}
		},
		save(jobId, verdicts) {
			try {
				const key = reviewStorageKey(jobId);
				if (Object.keys(verdicts).length === 0) {
					storage().removeItem(key);
				} else {
					storage().setItem(key, JSON.stringify(verdicts));
				}
			} catch {
				// Storage refused the write: the mark still shows on the open page.
			}
		}
	};
}

/** Marks kept in the browser's `localStorage`, under `larp:review:<jobId>`. */
export const localReviewStorage: ReviewStorage = webReviewStorage(() => window.localStorage);
