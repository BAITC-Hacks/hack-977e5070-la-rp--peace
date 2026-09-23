import { TYPE_LABELS } from '$lib/result/labels';
import type { Finding } from '$lib/result/types';

/**
 * Heading of a finding card: the finding title, or null when it is empty or only repeats the type
 * label the card already shows (titles such as «Конфликт интересов» in tech task §5.2).
 */
export function cardTitle(finding: Finding): string | null {
	const title = finding.title.trim();
	const repeatsType = title.toLowerCase() === TYPE_LABELS[finding.type].toLowerCase();
	return title === '' || repeatsType ? null : title;
}
