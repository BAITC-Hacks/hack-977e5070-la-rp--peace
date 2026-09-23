// P1.5: overlaps of zones and contradictions of functions are judgements about meaning, so their
// confidence is never shown above «средняя» (tech task §3.2), whatever the result says.

import type { Confidence, Finding, FindingType } from '$lib/result/types';

const CAPS: Partial<Record<FindingType, Confidence>> = {
	overlap: 'medium',
	contradiction: 'medium'
};

const RANK: Record<Confidence, number> = { low: 0, medium: 1, high: 2 };

/** Added to the basis of a confidence that was lowered to the cap. */
export const CAPPED_NOTE = 'Для этого типа находок уверенность не выше средней.';

/** The confidence to show for the finding: its own, lowered to the cap of its type. */
export function shownConfidence(finding: Finding): Confidence {
	const own = finding.evidence.confidence;
	const cap = CAPS[finding.type];
	return cap !== undefined && RANK[own] > RANK[cap] ? cap : own;
}

/**
 * The finding as it is shown: if its confidence is above the cap, a copy with the capped
 * confidence and `CAPPED_NOTE` added to the basis; otherwise the finding itself.
 */
export function withShownConfidence(finding: Finding): Finding {
	const confidence = shownConfidence(finding);
	if (confidence === finding.evidence.confidence) {
		return finding;
	}
	const note = [finding.evidence.confidence_note, CAPPED_NOTE].filter(Boolean).join(' ');
	return { ...finding, evidence: { ...finding.evidence, confidence, confidence_note: note } };
}
