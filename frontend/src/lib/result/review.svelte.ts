import { SvelteMap } from 'svelte/reactivity';

import type { Finding, Verdict } from './types';

/**
 * The employee's «Подтвердить / Отклонить» marks on the shown findings (I6). Starts from the
 * verdicts the result already carries; clicking the chosen verdict again takes it back.
 */
export class ReviewState {
	readonly #ids: readonly string[];
	readonly #verdicts = new SvelteMap<string, Verdict>();

	constructor(findings: Iterable<Finding>) {
		const list = [...findings];
		this.#ids = list.map((finding) => finding.id);
		for (const finding of list) {
			if (finding.review !== null) {
				this.#verdicts.set(finding.id, finding.review);
			}
		}
	}

	/** Number of findings that can be checked. */
	get total(): number {
		return this.#ids.length;
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
		if (!this.#ids.includes(id)) {
			return null;
		}
		if (this.#verdicts.get(id) === verdict) {
			this.#verdicts.delete(id);
			return null;
		}
		this.#verdicts.set(id, verdict);
		return verdict;
	}
}
