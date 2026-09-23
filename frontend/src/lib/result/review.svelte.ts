import { SvelteMap } from 'svelte/reactivity';

import type { ReviewStorage } from '$lib/review/storage';

import type { Finding, Verdict } from './types';

/** Where to remember the marks: the analysis they belong to and the storage that keeps them. */
export interface ReviewPersistence {
	jobId: string;
	storage: ReviewStorage;
}

/**
 * The employee's «Подтвердить / Отклонить» marks on the shown findings (I6). Starts from the
 * verdicts the result already carries, with the saved marks on top of them; clicking the chosen
 * verdict again takes it back. Without `persistence` the marks live only as long as the page.
 */
export class ReviewState {
	readonly #findings: readonly Finding[];
	readonly #verdicts = new SvelteMap<string, Verdict>();
	readonly #persistence: ReviewPersistence | undefined;

	constructor(findings: Iterable<Finding>, persistence?: ReviewPersistence) {
		this.#findings = [...findings];
		this.#persistence = persistence;
		for (const finding of this.#findings) {
			if (finding.review !== null) {
				this.#verdicts.set(finding.id, finding.review);
			}
		}
		const saved = persistence?.storage.load(persistence.jobId) ?? {};
		for (const [id, verdict] of Object.entries(saved)) {
			if (this.#find(id) === undefined) {
				continue;
			}
			if (verdict === null) {
				this.#verdicts.delete(id);
			} else {
				this.#verdicts.set(id, verdict);
			}
		}
	}

	/** Number of findings that can be checked. */
	get total(): number {
		return this.#findings.length;
	}

	/** Number of findings with a verdict. */
	get reviewed(): number {
		return this.#verdicts.size;
	}

	verdictOf(id: string): Verdict | null {
		return this.#verdicts.get(id) ?? null;
	}

	/** Sets the verdict, or clears it if it is already set; returns the verdict now in force. */
	toggle(id: string, verdict: Verdict): Verdict | null {
		const finding = this.#find(id);
		if (finding === undefined) {
			return null;
		}
		const next = this.#verdicts.get(id) === verdict ? null : verdict;
		if (next === null) {
			this.#verdicts.delete(id);
		} else {
			this.#verdicts.set(id, next);
		}
		this.#save(finding, next);
		return next;
	}

	#find(id: string): Finding | undefined {
		return this.#findings.find((finding) => finding.id === id);
	}

	/**
	 * Writes one mark through to the storage; only what differs from the result's own verdict is
	 * saved. The saved record is read afresh, so marks another page of the same analysis saved
	 * meanwhile are kept.
	 */
	#save(finding: Finding, verdict: Verdict | null) {
		if (this.#persistence === undefined) {
			return;
		}
		const { jobId, storage } = this.#persistence;
		const saved = storage.load(jobId);
		if (verdict === finding.review) {
			delete saved[finding.id];
		} else {
			saved[finding.id] = verdict;
		}
		storage.save(jobId, saved);
	}
}
