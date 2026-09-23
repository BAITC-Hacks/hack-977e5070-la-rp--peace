# HackAlem: organizational analysis research and proposed solution

Research date: 2026-09-23. Scope: official vendor documentation and product pages, opened and inspected. This is a capability comparison, not a hands-on product benchmark. Prices, procurement, regional availability, data residency, and Russian-language extraction accuracy were not verified.

The HackAlem workflow supplied for this research compares organizational structures, department regulations, and job descriptions before and after a reorganization. It must identify changed units, transferred or missing responsibilities, overlaps, and potential conflicts, with traceable document evidence.

My assessment: the strongest project is an evidence-linked reconciliation tool for responsibilities across two document sets. Existing products provide useful patterns for organizational modeling, responsibility modeling, process audits, and document comparison. The sources below do not establish that any one product delivers this exact workflow without configuration; they also do not establish that vendors cannot deliver it.

## What the actual task requires

Primary local source: `HackAlem AI_ ИИ-агент «Анализ организационной структуры и функционала».docx`, read directly from the original checkout. Sections 7, 9, 10, and 11 drive the design:

- Identify preserved, reorganized, and newly created units from the supplied documents.
- Compare functions across versions and across units, including potential losses, duplicates, and conflicts of interest.
- Attach the document and supporting clause/fragment to every material finding.
- Produce an understandable analytical conclusion and an upload/results interface.
- Demonstrate known changes on a control corpus; findings remain advisory and require human review.

External regulatory comparison and benchmarking are optional under section 8. Section 5 includes brief recommendations in the output; section 8 makes deeper redistribution recommendations optional. Include a short review action per finding and defer an optimization engine.

The scoring is 25 points each for functionality, technical implementation, and README/reproducibility, then 15 for practical value and 10 for development potential/originality. A reproducible end-to-end demonstration should therefore take priority over a large feature list.

## What the supplied examples reveal

I inspected the two untracked DOCX samples in the original checkout's `test_data/`; they were not added to this research commit. These are observations from the documents, not results from a completed AI implementation:

| Observation | Design implication |
| --- | --- |
| Edition 8 is dated 25 June 2021; edition 9 is dated 23 December 2022. Their bodies contain approximately 84,000 characters each. | Use explicit before/after selection and verify version metadata. Process logical sections with inherited context. |
| Section 3.4 in edition 8 lists ДНМ and ДККМ; edition 9 lists ДИТААД, ДОА, ДНМ, and ДККМ. | Demonstrate newly listed and preserved units with both source clauses. The new entries alone do not prove legal creation or a particular split/merge history. Seek supporting organizational orders and functional continuity before stronger claims. |
| Sections 1.5 and 1.6 distinguish functional supervision by the board from administrative supervision by the president. | Model reporting relationships by type. A single `parent_id` is insufficient for all governance reasoning. |
| The prohibition section headed “Главный аудитор и работники БВА не имеют права” moves from 5.9 to 5.8. | Clause number is a source locator, not a stable semantic identity. Renumbering must not become a lost-function finding. |
| Some paragraphs combine several numbered clauses; list items inherit the parent clause's actor and meaning. | A paragraph is not necessarily one responsibility. Preserve clause/list hierarchy, inherited actors, and prohibitions. |
| Section 4.4 in edition 9 discusses participation in subsidiary governance together with safeguards for independence and objectivity. | Read conditions and safeguards before flagging an apparent self-review conflict. A short excerpt can reverse the meaning. |

These observations support a real first demonstration. They do not establish an independently labeled lost-function or duplication case. Obtain organizer labels, or create clearly marked synthetic test variants separately from the organizer's data.

## Comparison

| Solution | Vendor-documented capabilities | Assessment for this task | Pattern to borrow |
| --- | --- | --- | --- |
| **Orgvue** | Models individual positions and entire functions; compares alternative structures and scenarios; connects workforce, structure, and cost data. Its activity-analysis method builds a taxonomy and links employees to activities through surveys. [Organization modeling](https://www.orgvue.com/solutions/organization-modeling/), [activity-driven organization design](https://www.orgvue.com/resources/articles/how-to-do-activity-driven-organizational-design/). | Closest conceptual match for comparing organizations. The inspected material focuses on organized workforce/activity data; it does not verify clause-level extraction and reconciliation of arbitrary Russian Word/PDF/Excel document sets. | Model the work separately from unit names. Compare both structure and responsibility assignments. |
| **SAP Signavio Process Manager** | Supports task attributes for responsible, accountable, consulted, and informed roles. SAP documents connecting these attributes to dictionary entries in an Organizational Units category. [SAP KBA 3161065](https://userapps.support.sap.com/sap/support/knowledge/en/3161065). | Useful responsibility model. The verified capability assumes modeled tasks and dictionary links; automatic creation of those links from this task's source documents remains unverified. | Preserve the distinction between performing, approving, being consulted, and being informed. Matching subject matter alone is insufficient to establish duplication. |
| **Celonis** | Describes reconstructing business processes from IT event logs. Its internal-audit article gives an example in which the same person approved a credit check and credited an invoice, violating the organization's guidelines. [Process intelligence and internal audit](https://www.celonis.com/blog/process-mining-and-internal-audit-a-match-made-in-heaven). | Strong reference for checks against actual execution. Our input is formal assignments in documents, so we can flag potential incompatible assignments, not demonstrate that a violation occurred in a transaction. | Encode incompatible actions against the same business object, supported by a policy or explicit review rule. Keep the finding and the supporting events or clauses linked. |
| **Litera Compare** | Compares Word, Excel, PowerPoint, and PDF documents; provides redlines, change navigation, and synchronized original/modified/redline views. Its product sheet describes text, table, chart, image, and formatting comparison. [Litera Compare product sheet](https://info.litera.com/rs/046-QLX-552/images/Litera-Compare.pdf). | Strong interaction model for checking evidence. A textual deletion alone cannot establish a lost function when another unit's document may now contain a paraphrased assignment. The inspected sheet does not verify organization-wide semantic reassignment detection. | Show the original passages next to the finding and make changes easy to review. Treat document comparison as supporting evidence for semantic analysis. |
| **ABBYY FineReader Engine / FineReader PDF** | The Engine's comparison module supports Word, Excel, PDF, and image formats; focuses on added, removed, or changed text; and exposes results through an API or Word/XML output. FineReader PDF documents side-by-side comparison and saving differences as annotated PDF or Word tracked changes. [Engine comparison module](https://www.abbyy.com/ocr-sdk/features/compare-documents/), [FineReader PDF comparison workflow](https://pdf.abbyy.com/how-to/compare-documents/). | Relevant ingestion and comparison infrastructure, especially for scans. Product pages do not verify semantic department matching, split/merge detection, or responsibility-conflict analysis. Integrating a licensed SDK is a separate implementation/procurement decision. | Preserve source locations through OCR and parsing; retain originals and provide a reviewable difference report. |

## Recommended approach for the hackathon

The following is my design recommendation, not a claim about a vendor's implementation.

Build a compact pipeline:

```text
Before / after document sets
  -> parsed source blocks with stable locations
  -> units and atomic responsibility assignments
  -> candidate unit / function mappings
  -> evidence checks and exception detection
  -> reviewable findings and analytical conclusion
```

1. **Preserve provenance before invoking a model.** Every source block needs a document ID, version side, location, and exact text. For DOCX use clause/paragraph/table location; do not invent stable page numbers. For PDF retain page and, when available, coordinates. For Excel retain sheet and cell/range. A model selects block IDs; application code resolves their text and locations.
2. **Extract atomic assignments.** Use a representation such as unit, action, object, scope, responsibility kind, and source IDs. Separate “prepares purchasing requests” from “approves purchasing requests.” Split compound sentences when they assign distinct duties. Keep the original wording alongside normalized labels.
3. **Allow many-to-many mappings.** A unit can split or merge, and responsibilities can move separately from its name. Generate candidate matches using normalized names and semantic similarity, then classify relationships with a model using cited clauses. Permit unresolved mappings; do not force every old unit into a one-to-one match.
4. **Search the entire after-set before flagging a loss.** A responsibility absent from the successor department's regulation may appear in another department or a job description. Distinguish “not found in supplied documents” from “explicitly abolished.” Missing or unreadable input should lower completeness, rather than produce confident loss claims.
5. **Separate overlaps from conflicts.** An overlap requires comparable action, object, scope, and responsibility kind across units. A potential conflict requires incompatible actions and an explicit policy or review rule. Shared participation, different territories, and execution versus consultation can be legitimate.
6. **Generate the conclusion from findings already validated.** Each factual statement should link to a finding whose cited blocks exist and contain the quoted text. Missing functions also need an account of the search coverage; a citation to the old function supports its previous existence, not proof of absence in all later material.

### Responsibility model and analysis rules

Represent the organization as structured records and relations; a graph database is unnecessary for the prototype:

- `Document`: file identity/hash, side, edition/effective date, document type, parse coverage.
- `SourceBlock`: document ID, exact text, heading/list context, clause and original location.
- `Unit` and `ReportingRelation`: stable analysis IDs, names/aliases, relation type, supporting sources.
- `Assignment`: owner, action, object, scope, output, frequency, responsibility kind, obligation/permission/prohibition, conditions, source IDs.
- `Mapping`: sets of before/after IDs, relation type, explanation, evidence, unresolved portions.
- `Finding`: type, affected assignments, supporting sources, counterevidence, search coverage, review state.

An assignment such as “prepare the quarterly audit plan” must remain distinct from “approve the audit plan.” Do not discard frequency, jurisdiction, business object, negation, or exceptions during normalization. Do not infer a department's duties solely from its name.

Match functions globally across units after producing tentative unit mappings. Permit one-to-many and many-to-one relationships: an old compound responsibility may survive in several new clauses. Check partial loss explicitly; matching only one part must not mark the whole responsibility as preserved.

Use these interpretation rules:

| Candidate finding | Required check |
| --- | --- |
| Preserved / moved | Equivalent responsibility remains; determine whether the owner changed. |
| Modified / partially covered | Identify precisely which action, scope, output, or frequency changed or remains unmatched. |
| Potential loss | Search all supplied after documents, resolve aliases and paraphrases, check parsing completeness, and record examined candidates. Display “not found in the supplied after-set” unless explicit abolition is evidenced. |
| Potential duplicate | Same responsibility kind and overlapping scope assigned to distinct owners. Exclude a parent unit restating a child's assignment and repeated descriptions of the same owner's duty in multiple documents. |
| Potential conflict | Incompatible assignments within the same scope, plus a cited independence/prohibition rule where available. Consider safeguards and exemptions. Without a documented rule, label the concern as a hypothesis needing review. |
| Unresolved | Insufficient evidence, missing pages, ambiguous owner, conflicting documents, or an unclear mapping. Never silently force a confident category. |

Use lexical and semantic retrieval to propose candidate matches; have the model compare the original clauses and classify the relationship. Retrieval scores indicate relevance, not proof of equivalence or calibrated confidence. The retrieval-then-reranking pattern is documented by [Sentence Transformers](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html); adapting it to responsibility matching is this proposal, not a measured result. For this small corpus, section-level exhaustive passes can avoid a dedicated search service. Expand candidate search before accepting an unmatched result.

Keep every extracted before-assignment accounted for as matched, partially matched, not found, or unresolved. Measure extraction coverage separately: accounting for all extracted items does not prove that extraction found all source responsibilities.

### Bounded agent behavior

Use one orchestrator with extraction, matching, and evidence-verification stages. A separate review pass can use the same model. The useful agentic behavior is a bounded corrective loop:

1. Propose a finding with source IDs and a short evidence-based explanation.
2. Check schema validity, ID existence, exact source spans, and whether the evidence supports the relation.
3. For weak evidence, retrieve neighboring clauses, other owners' assignments, and relevant exceptions.
4. Revise, retain as unresolved, or discard the finding; enforce a retry and token budget.
5. Generate the summary only from the resulting findings.

Application code supplies exact quotes and locations from stored source blocks. Quote existence is a mechanical check; entailment and completeness still need semantic review and human evaluation. Log completed stages and concise explanations for the user. Document contents are analysis data and must not override the agent's instructions. External web search is for this research; the core document analysis should use the uploaded corpus.

### Implementation fit with this repository

At research time, concurrent work in the shared checkout's `pyproject.toml` declared FastAPI, Pydantic settings, SQLAlchemy, python-docx, PyMuPDF, and openpyxl; these additions were still uncommitted. The clean research branch starts from a smaller committed baseline. The frontend specification selects SvelteKit/Svelte 5. Coordinate with the backend owner and reuse those planned choices. This research makes no dependency changes and approves none; its validation uses the existing locked development environment.

| Concern | Proposed prototype choice |
| --- | --- |
| Word | python-docx for DOCX paragraphs and tables in document order; preserve list/heading context and inspect numbering/OOXML where needed. The API exposes ordered inner content and documents limits around revision marks and nested tables. [python-docx documentation](https://python-docx.readthedocs.io/en/latest/api/document.html). |
| PDF | PyMuPDF text blocks with page/rectangle references. Detect empty or unusable text extraction and report incomplete coverage. Its documentation describes block/word coordinates. [PyMuPDF text extraction](https://pymupdf.readthedocs.io/en/latest/recipes-text.html). |
| Excel | openpyxl; preserve worksheet, cell/range, headers, and hierarchy inferred from the actual sheet. Use cell content without executing workbook macros. [openpyxl tutorial](https://openpyxl.readthedocs.io/en/stable/tutorial.html). |
| API and persistence | FastAPI, typed result objects, original files plus persisted intermediate JSON and metadata in SQLite/SQLAlchemy or the team's existing database. Avoid introducing a separate vector/graph service for a small control corpus. |
| AI | An available, authorized model endpoint tested on Russian terminology and structured extraction. Cache results by document/prompt/model version; record latency and failures. Provider credentials and budget need to be available for implementation. |
| UI | Russian labels, two upload sets, unit/function tables, issue filters, a source drawer, and a cited conclusion. A finding should open both original passages with one click. |

The minimum format target is DOCX, text-based PDF, and XLSX. Legacy DOC/XLS, scanned pages, and graphical organization charts require conversion, OCR, or visual extraction paths; do not silently accept them as fully analyzed. The organizer's actual control formats determine whether those paths are required for the demo. [Docling's document model](https://docling-project.github.io/docling/concepts/docling_document/) is a possible later ingestion option: it represents hierarchy, tables, provenance, and available layout coordinates. It is not an installed dependency or a complete organizational-analysis solution.

The existing `.agents/frontend.md` is broader than the six-hour core and its API is explicitly proposed. Agree with the backend owner before implementing against it. In particular, the proposed function match shape is one-before/one-after, and its statuses omit unresolved/partial coverage. Unit changes already allow multiple IDs. Discuss these function-mapping and uncertainty requirements, plus typed reporting relationships, without changing the shared contract unilaterally.

### Six-hour delivery plan

This is a proposed allocation, assuming three contributors and model access at kickoff. Assign concrete files and agree shared interfaces once; do not create replacement code for another owner's missing component.

| Time | Team outcome |
| --- | --- |
| 0:00–0:30 | Inspect the control inputs; agree source IDs, assignment/mapping/finding schemas, ownership, format scope, and a small labeled evaluation set. Confirm model access. |
| 0:30–2:00 | In parallel: contributor A builds parsing/provenance; B builds extraction and semantic comparison; Sula builds upload/results/source components against the agreed, available API. |
| 2:00–3:00 | Complete one real upload-to-result flow. Verify a unit change and open the exact original clause in the UI. Start executable run instructions. |
| 3:00–4:30 | Add whole-corpus loss checks, overlap/conflict checks, uncertainty states, and the cited conclusion. Test transfers and benign overlaps as negative controls. |
| 4:30–5:15 | Integrate all supported formats; check source integrity, model failures, retries, and the organizer's known cases. Finish architecture/run documentation. |
| 5:15–6:00 | Feature freeze. Fix failures, run required checks, reproduce from a clean environment, and rehearse the demo. |

Prioritize three views: upload, progress, and results with a source panel. Within results, tables are sufficient for unit and function changes. A large interactive organization tree, history management, broad benchmark search, multiple export formats, and enterprise connectors can follow the working core. Do not sacrifice evidence navigation for visual complexity.

### Evaluation and demo

Create a small human-labeled set covering preserved and renamed units, split/merge mappings where evidence exists, function transfer, partial and complete omission, genuine overlap, benign shared participation, and a policy-supported conflict. Add renumbering, negation, inherited responsibility, safeguards, and missing-input cases. Distinguish synthetic cases from organizer examples.

Report measured unit-mapping accuracy, function-matching precision/recall, loss/duplicate detection precision/recall, citation validity, unresolved rate, runtime, and model cost. Do not present self-reported model confidence as accuracy. A useful release gate is that every displayed factual finding resolves to its actual supporting source and every known organizer control case is detected with correct evidence; measure semantic support separately from whether a link opens.

The demo should show: upload editions → detect the changed structure → follow one responsibility across units → inspect one exception → click its exact evidence → read the short conclusion. If the available real samples do not contain a labeled loss or duplicate, disclose that and use a separately labeled synthetic fixture for that check.

For three people and six hours, divide ownership by concrete files: ingestion/provenance, matching/findings, and UI/review. Prioritize upload, unit and function mapping tables, lost/duplicate/conflict findings, a source panel, and a cited conclusion. Evaluate the smallest complete workflow early against a known reorganization, a moved function, a missing function, a duplication, and a benign shared responsibility. Use the same sample to verify every citation.

Defer advanced graph visualizations, broad benchmarking, external regulatory discovery, enterprise integrations, and exhaustive workflow history. They do not substitute for accurate matches and valid evidence. This recommendation does not authorize dependency changes or modifications to the shared API contract.

## Research limits

- These are vendor-documented capabilities, not measured accuracy or delivery guarantees. Marketing claims about speed and benchmark superiority were deliberately not adopted.
- SAP's public KBA was readable and is the basis for the Signavio row. Several SAP Help Portal guide URLs returned empty bodies or redirected to page-not-found, so unverified guide details were excluded.
- No licensed product was executed against the organizer's control corpus. Exact format handling, Russian terminology, scans, large corpora, and source-link fidelity require a representative trial.
- A production comparison should ask vendors to run the same before/after corpus and score unit matching, function coverage, false overlaps, policy-backed conflicts, and citation correctness.
