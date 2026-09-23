# Stage 5.1: first backend increment

Implemented against methodology/05_1_document_diff.md. No model calls or new dependencies.

POST /api/document-diffs:

```json
{"before_document_id": 1, "after_document_id": 2, "confirmed": true}
```

The caller explicitly confirms the pair and its order. Existing stage-1 text and node trees are
read without modification. GET /api/document-diffs/{comparison_id} retrieves the saved result.

The response contains both original texts, independently addressed fragments, source paths,
Unicode [start,end) ranges, review candidates and token-level exact diff operations.
Parent own text is separate from children; uncovered text is retained as fallback ranges.
Whitespace gaps remain available in the original text and fragment list.

Unique exact matches require matching introductory context. Other fragments remain
needs_review: absence from the top five fuzzy candidates does not establish addition/deletion.
All opposite fragments remain in the response, including already matched ones, for reviewing splits.

The frontend can submit a new comparison with groups:
```json
{
  "before_document_id": 1,
  "after_document_id": 2,
  "confirmed": true,
  "before_fingerprint": "copy from previous response.before.fingerprint",
  "after_fingerprint": "copy from previous response.after.fingerprint",
  "groups": [
    {"before": ["copy fragment ID"], "after": ["copy fragment ID"], "reason": "Reviewed corresponding clauses"}
  ]
}
```

Groups support one-to-one, splits, merges and reworked blocks. A user-confirmed empty side
denotes an addition/deletion. References are checked against the selected sides; duplicate
accepted use is rejected. Manual additions/deletions require reviewing the whole opposite document.
Every request saves a new comparison. Reading an old result marks it stale if source extraction changed.

Flags include unchanged, modified, renumbered, moved, moved_with_parent, split, merged, reworked,
added and deleted. Candidate scores are ranking scores, not probabilities. The API sends structured
text spans, not HTML; render document content as text. JavaScript clients must convert Unicode
code-point offsets when using UTF-16 string indices.

Not yet implemented: automatic document-family/order suggestions, AI verification and semantic
search, automatic split/merge recognition, dedicated table-header interpretation, frontend integration.
Therefore this is a usable first increment, not a claim of complete methodology 5.1 coverage.
