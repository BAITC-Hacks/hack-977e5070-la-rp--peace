import { describeError } from '$lib/api/errors';
import type { ExtractionStatus } from '$lib/api/registries';

export const REGISTRY_POLL_MS = 2000;

/** A read-only stage view; a failed refresh never turns stored records into an empty result. */
export class RegistryView<T extends { status: ExtractionStatus }> {
	data = $state.raw<T | null>(null);
	error = $state<string | null>(null);
	loading = $state(false);
	readonly #load: () => Promise<T>;
	#timer: ReturnType<typeof setTimeout> | undefined;
	#stopped = false;
	#request = 0;

	constructor(load: () => Promise<T>) {
		this.#load = load;
	}

	start(): void {
		void this.refresh();
	}

	stop(): void {
		this.#stopped = true;
		this.#request += 1;
		clearTimeout(this.#timer);
	}

	async refresh(): Promise<void> {
		if (this.loading || this.#stopped) return;
		clearTimeout(this.#timer);
		const request = ++this.#request;
		this.loading = true;
		this.error = null;
		try {
			const data = await this.#load();
			if (this.#stopped || request !== this.#request) return;
			this.data = data;
			if (data.status === 'running' || data.status === 'not_started') {
				this.#timer = setTimeout(() => void this.refresh(), REGISTRY_POLL_MS);
			}
		} catch (error) {
			if (!this.#stopped && request === this.#request) this.error = describeError(error);
		} finally {
			if (!this.#stopped && request === this.#request) this.loading = false;
		}
	}
}
