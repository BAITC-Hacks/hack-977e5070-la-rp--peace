/** A piece of the compared text: kept, only in «до» (`delete`) or only in «после» (`insert`). */
export type WordOp = 'equal' | 'delete' | 'insert';

export interface WordPart {
	readonly op: WordOp;
	readonly text: string;
}

/**
 * Largest LCS table (tokens «до» × tokens «после», after the common start and end are cut off)
 * the diff will build. Above it the differing middle is shown replaced as a whole, so a very
 * long clause cannot freeze the page or exhaust memory.
 */
export const MAX_LCS_CELLS = 1_000_000;

/** Words, runs of whitespace and single punctuation marks, so that no text is ever dropped. */
const TOKEN = /[\p{L}\p{N}]+|\s+|[^\p{L}\p{N}\s]/gu;
const BLANK = /^\s+$/;

export function tokenize(text: string): string[] {
	return text.match(TOKEN) ?? [];
}

/** Word diff via the longest common subsequence of tokens; ties put deletions first. */
function lcsDiff(before: readonly string[], after: readonly string[]): WordPart[] {
	const n = before.length;
	const m = after.length;
	const width = m + 1;
	// lengths[i * width + j]: LCS length of before[i..] and after[j..].
	const lengths = new Uint32Array((n + 1) * width);
	for (let i = n - 1; i >= 0; i--) {
		for (let j = m - 1; j >= 0; j--) {
			lengths[i * width + j] =
				before[i] === after[j]
					? lengths[(i + 1) * width + j + 1] + 1
					: Math.max(lengths[(i + 1) * width + j], lengths[i * width + j + 1]);
		}
	}

	const parts: WordPart[] = [];
	let i = 0;
	let j = 0;
	while (i < n && j < m) {
		if (before[i] === after[j]) {
			parts.push({ op: 'equal', text: before[i] });
			i++;
			j++;
		} else if (lengths[(i + 1) * width + j] >= lengths[i * width + j + 1]) {
			parts.push({ op: 'delete', text: before[i++] });
		} else {
			parts.push({ op: 'insert', text: after[j++] });
		}
	}
	for (; i < n; i++) {
		parts.push({ op: 'delete', text: before[i] });
	}
	for (; j < m; j++) {
		parts.push({ op: 'insert', text: after[j] });
	}
	return parts;
}

/** Joins neighbouring parts of the same kind and drops empty ones. */
function merge(parts: readonly WordPart[]): WordPart[] {
	const merged: WordPart[] = [];
	for (const part of parts) {
		if (part.text === '') {
			continue;
		}
		const last = merged.at(-1);
		if (last?.op === part.op) {
			merged[merged.length - 1] = { op: part.op, text: last.text + part.text };
		} else {
			merged.push(part);
		}
	}
	return merged;
}

/**
 * «<del>Отдел</del><ins>Департамент</ins> <del>кадров</del><ins>персонала</ins>» reads badly: a
 * space shared by two replacements is folded into them, giving «<del>Отдел кадров</del>
 * <ins>Департамент персонала</ins>». Runs with deletions only or insertions only stay as they are.
 */
function foldReplacements(parts: readonly WordPart[]): WordPart[] {
	const result: WordPart[] = [];
	let run: WordPart[] = [];
	let held = '';

	const flush = () => {
		const deleted = run.filter((part) => part.op !== 'insert');
		const inserted = run.filter((part) => part.op !== 'delete');
		if (deleted.length < run.length && inserted.length < run.length) {
			result.push({ op: 'delete', text: deleted.map((part) => part.text).join('') });
			result.push({ op: 'insert', text: inserted.map((part) => part.text).join('') });
		} else {
			result.push(...run);
		}
		run = [];
	};

	for (const part of parts) {
		if (part.op !== 'equal') {
			if (held !== '') {
				run.push({ op: 'equal', text: held });
				held = '';
			}
			run.push(part);
		} else if (run.length > 0 && BLANK.test(part.text)) {
			held += part.text;
		} else {
			flush();
			result.push({ op: 'equal', text: held + part.text });
			held = '';
		}
	}
	flush();
	result.push({ op: 'equal', text: held });
	return merge(result);
}

/**
 * Word-by-word difference between two texts, in reading order. Joining the `equal` and `delete`
 * parts gives `before`; joining the `equal` and `insert` parts gives `after`.
 */
export function diffWords(before: string, after: string): WordPart[] {
	if (before === after) {
		return merge([{ op: 'equal', text: before }]);
	}
	const a = tokenize(before);
	const b = tokenize(after);

	let start = 0;
	while (start < a.length && start < b.length && a[start] === b[start]) {
		start++;
	}
	let endA = a.length;
	let endB = b.length;
	while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
		endA--;
		endB--;
	}

	const middleA = a.slice(start, endA);
	const middleB = b.slice(start, endB);
	const middle =
		middleA.length * middleB.length > MAX_LCS_CELLS
			? [
					{ op: 'delete' as const, text: middleA.join('') },
					{ op: 'insert' as const, text: middleB.join('') }
				]
			: lcsDiff(middleA, middleB);

	return foldReplacements(
		merge([
			{ op: 'equal', text: a.slice(0, start).join('') },
			...middle,
			{ op: 'equal', text: a.slice(endA).join('') }
		])
	);
}
