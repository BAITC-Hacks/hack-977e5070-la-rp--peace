# Backend Spec

**Owner:** Alim (backend, DB). **Methodology:** Marinadec — *how* units and functions are
compared is theirs (`methodology/`, `src/la_rp_peace/analysis/`). The backend owns
everything around it: ingestion, storage, the HTTP API, running analyses, and serving results.
Source of truth: the organiser's tech task (docx in the repo root). API contract shared with
the frontend: [`frontend.md`](frontend.md) §4.

## Stack

| Concern | Choice | Why |
|---|---|---|
| API | FastAPI + uvicorn, sync endpoints | Typed, OpenAPI at `/docs` for Sula for free |
| DB | SQLite file `data/larp.sqlite3`, SQLAlchemy 2 sync ORM; foreign keys + WAL on every connection | No server; the methodology schema targets SQLite |
| Schema | `src/la_rp_peace/schema.sql`: the tables of methodology stage 1 (§9) plus `document_files` and `documents.doc_set`, applied to a new DB — no migrations | Methodology describes the tables, the backend owns the executable schema; schema change → delete `data/larp.sqlite3` |
| Parsing | python-docx, pymupdf, openpyxl → `original_text` + `source_map`; **AI parsing profile (OpenAI) always** | Methodology §1–§2 |
| AI | `openai` SDK, JSON mode, model from `OPENAI_MODEL`; model regexes run with the `regex` engine under a timeout | No model-supplied code is executed |
| Jobs | In-process `ThreadPoolExecutor(PARSER_WORKERS)`; pending documents requeued on startup | No Celery/Redis |
| Tests | pytest; recorded model answers in `tests/fixtures/profiles/`; `pytest -m live` calls OpenAI | Suite runs offline |

Run:

```bash
uv run uvicorn la_rp_peace.api.app:create_app --factory --reload   # http://localhost:8000/docs
uv run python -m la_rp_peace.serve   # whole app: builds frontend/ (Node 20+), serves UI + API on http://localhost:8000
uv run python -m la_rp_peace.serve --no-build   # same, reusing the last UI build
```

Config (env or `.env`, see `.env.example`): `DATABASE_URL`, `MAX_UPLOAD_MB`, `CORS_ORIGINS`,
`LOG_LEVEL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`, `OPENAI_REASONING_EFFORT` (default `low`), `PROFILE_MAX_CHARS`,
`PROFILE_RETRIES`, `PARSER_WORKERS`, `ENTITY_BLOCK_MAX_CHARS` (12000), `ENTITY_RETRIES` (2).
Without the key and model, uploads return 503.

## Layout

```
src/la_rp_peace/
  config.py, db.py, models.py (ORM over schema.sql), enums.py, schema.sql
  quotes.py       verbatim quote matching (whitespace-insensitive, nothing else forgiven)
  navigation.py   anchor / path / file location of stored nodes
  sources.py      citation verification -> SourceRef
  ingestion/
    extract/      docx.py, pdf.py (line -> paragraph recovery), xlsx.py -> Extraction
    prompt.py     what the model sees (sampled above PROFILE_MAX_CHARS)
    profiler.py   OpenAIProfiler
    profile.py    profile schema, compilation, self-checks of examples
    tree.py       applies a profile: sections, clauses, lists, headings, tables, service
    checks.py     methodology §8 checks -> parsing_issues
    metadata.py   card fields verified against quotes -> metadata_evidence
    analysis.py   answer -> checks -> feedback to the model, up to PROFILE_RETRIES
    pipeline.py   register upload, background parsing, one-transaction save, post-parse stages
  llm.py          ChatModel protocol + OpenAIChatModel (JSON mode), shared by all stages
  entities/       stage 2 (organisational entities), see below
    blocks.py     tree -> blocks (section or split at child boundaries, ancestors as context)
    prompt.py     methodology rules, block and whole-document review messages
    answers.py    pydantic shapes of the model's answers
    verify.py     quotes in nodes of THIS document, supports vocabulary, refs, statuses
    conversation.py  answer -> checks -> feedback, up to ENTITY_RETRIES
    registry.py   per-document registry E<n>: upserts, ambiguous parents, cycle refusal, merges
    extract.py, consolidate.py, checks.py (methodology §8), pipeline.py (EntityStage, save)
  api/            app.py (factory), documents.py, entities.py, sources.py, schemas.py, deps.py
  analysis/       Marinadec — comparison stages (not yet present)
```

## Parsing pipeline (methodology stage 1)

1. `POST /api/documents` registers the file (sha256, size, format, `doc_set`) as `pending`
   and returns **202**; a worker takes it from there. Poll `GET /api/documents/{id}`.
2. Extraction produces `original_text` (blocks joined by newlines, table cells by tabs,
   whitespace normalised inside blocks) and a `source_map` of `{start, end, location}`: DOCX
   body position, PDF page per line, XLSX sheet/row/column. PDF page numbers are kept as blocks.
3. The model receives the document as `@offset [style] text` lines and answers
   `{metadata, parsing_profile}`. The profile is validated (schema, regex compilation with
   timeout, its own positive/negative examples), applied to the whole document, and the tree
   checked; metadata quotes are located in `original_text`. Every problem goes back to the
   model (numbering gaps as advisories: accepted if the next answer confirms them); after
   `PROFILE_RETRIES` the best answer is kept.
4. One transaction writes text, source map, card + evidence, profile (with `studied_ranges`,
   `attempts`), nodes and issues. Status: `validated` without open blocking issues, otherwise
   `needs_review`. Extraction or model failures -> `needs_review` + blocking issue.

On the control documents, DOCX and the Word-exported PDFs in `test_data/converted/` produce
identical trees (tests enforce it): 14 sections, glued 3.10–3.12 and `10.Контроль качества`
split out, two separate lists in 9.3, TOC and approval stamp as `service`, `5.5.3. ;` of
ed. 8 reported as `empty_content`.

## Entity extraction (methodology stage 2)

Chained automatically after stage 1 (`EntityStage`, name `entities`); `documents.entities_status`
goes `not_started → running → done | needs_review | failed`. Each document is processed alone.

1. `plan_blocks` turns the tree into blocks: front matter (approval stamp, title), then one
   block per section; sections above `ENTITY_BLOCK_MAX_CHARS` are split at child boundaries,
   each part carrying its ancestors' headings/intro texts as `(контекст)` lines. TOC lines and
   page numbers are dropped. Lines are `[node <id>] <path> | <text>`.
2. Blocks are read in order. The model sees the card, the registry so far (`E<n>: name …`)
   and the block, and answers mentions (`E<n>` = known object, other refs = new), parents
   with status, relations (functional subordination, reports_to, … — never the parent) and
   unclear cases. Each mention has `type` (the document's wording) and a normalised `category`
   (organization, governing_body, block, department, division, group, position, collective,
   other, unclear — rules in `entities/prompt.py`; later stages compare objects of one category;
   a category conflict keeps the first with an issue, merges across categories are refused,
   `unclear` needs review). Every claim needs a source `{node_id, quote, supports}`; quotes must be
   verbatim in a node of this document. Problems go back to the model; after
   `ENTITY_RETRIES` or on a request error the block is `failed` (never `none`) + blocking issue.
3. A whole-document review merges duplicates only with a `same_entity` source and settles
   parents with evidence. Equal names never merge by themselves; a second, different parent
   makes the parent `ambiguous` (candidates kept in `entities.parent_candidates`); cycles are refused.
4. Final checks (§8): parents exist, no cycles, name sources present, root/resolved without a
   `parent` source falls back to `unknown`. Entities with an open issue get `needs_review`,
   the others `checked`; the document is `needs_review` if any issue is blocking or a block
   failed, else `done`. One transaction writes the result.
5. Re-runs (§4): every source records its block (`entity_sources.block_node_id`, NULL for the
   review), so a block's new verified answer replaces its previous contribution; objects also
   confirmed by other blocks stay. A block that fails keeps its previous contribution (sources
   re-checked against the current node texts; stale ones dropped with an issue) and is marked
   `failed` + blocking issue. Unchanged objects keep their `entities.id` (unique match on
   name/alias + category + parent; rows updated in place), relations keep ids by ends + type;
   objects no longer found are deleted. A crash (`failed` status) leaves the stored result as is.

## Traceability contract (every conclusion -> exact words)

Non-negotiable for everything the analysis produces (tech task §7.4, §9):

1. **A finding cites, never paraphrases.** Each claim carries citations
   `{node_id, quote}` for the side(s) it is about; a change cites **both** documents
   (e.g. «unit created» cites the before list without it and the after list with it).
2. **The quote is copied word for word** from a node's `text` (`GET /api/documents/{id}/nodes`).
   `sources.resolve_source()` (HTTP: `POST /api/sources/resolve`) rejects any quote not found
   verbatim in the node — the analysis must drop or retry such a finding, never show it.
3. **A resolved source tells a person where to look** in the original file:

   | Field | Example |
   |---|---|
   | `document_name`, `set` | `…редакция_9….pdf`, `after` |
   | `path` | `Разд. 3 «Структура и организация работы внутреннего аудита» › п. 3.4 › подп. «а»` |
   | `location` | `{"page": 6}` (PDF), `{"paragraph": 103}` (DOCX), `{"sheet", "row"}` (XLSX) |
   | `quote`, `context`, `start`, `end` | the cited words, the node text, offsets in it for highlighting |
   | `source_start`, `source_end` | offsets in the document's `original_text` |

   Clause numbers are part of the document text, so `path` + `quote` find the spot with
   Ctrl+F in Word or any PDF viewer.

`GET /api/nodes/{node_id}` returns a node as a source quoting its whole text. The same
quote check backs the metadata card: every card value has quotes in `metadata_evidence`.

## Slices

### 1. Ingestion, AI profile, document API — **done**

Endpoints: `POST/GET /api/documents`, `GET/PATCH/DELETE /api/documents/{id}`,
`GET /api/documents/{id}/nodes|issues|profile|file`, `GET /api/nodes/{id}`,
`POST /api/sources/resolve`, `GET /api/health`.

### 1b. Organisational entities (stage 2) — **done**

`GET /api/documents/{id}/entities` (parent, status, candidates, aliases, `entity_type`, `category`, roles, review status,
sources `{node_id, path, location, quote, start, end, supports}`),
`GET /api/documents/{id}/entity-relations`, `GET /api/documents/{id}/entity-report` (block marks,
issues, `entities_status`), `POST /api/documents/{id}/entities` → 202, re-runs stage 2 and the
stages after it (409 without a tree, 503 without a model). `DocumentOut` carries `entities_status`.

### 2. Analyses and live progress

- Tables: `analyses` (name, status `queued|running|done|failed|cancelled`, document ids, error,
  timestamps), `analysis_stages` (name, order, status), `analysis_events` (log lines for SSE replay).
- `POST /api/analyses` → queue on the executor; `GET /api/analyses`, `GET /api/analyses/{id}`,
  `POST …/cancel` (cooperative flag checked between stages), `DELETE`.
- `GET /api/analyses/{id}/events` — SSE (`stage`, `log`, `done`, `error`) via `StreamingResponse`;
  replays stored events first so a reconnecting browser misses nothing.

### 3. Seam for the methodology (agree with Marinadec before coding)

Backend calls an ordered list of stages from `la_rp_peace.analysis`; each stage receives the
analysis context (documents + node trees + earlier stage outputs + a `report(message)` callback
for the live log) and returns typed results. Findings must carry `SourceRef`s = node id +
quoted span, never free text. Stage names map 1:1 to the frontend stepper (frontend.md §2.2).
The OpenAI client and settings from stage 1 are reusable; prompts are the methodology's.

### 4. Findings, verdicts, results

- Tables: `unit_changes`, `function_matches`, `overlaps` (duplicates and conflicts of interest),
  `citations`, `recommendations`, `verdicts` — shapes per frontend.md §4 `AnalysisResult`.
- `GET /api/analyses/{id}` embeds `result` when done.
- `PUT /api/analyses/{id}/findings/{finding_id}/verdict` — the responsible employee's check (§9).

### 5. Export

`GET /api/analyses/{id}/export?format=docx` — conclusion, findings tables, citations and verdicts
rendered with python-docx. PDF is the frontend's print stylesheet, not a backend job.

### 6. Optional (§8)

Regulatory and benchmark documents are already accepted (`set=regulatory|benchmark`); their
comparison stages come from the methodology.

### 7. Activities (methodology stage 3) — **done**

`src/la_rp_peace/activities/`: `ActivityStage` (`name = "activities"`) is a post-parse stage
after entities. It reads the tree and the stage 2 registry **from the database only** and runs
when `entities_status` is `done`/`needs_review`; otherwise `activities_status` stays
`not_started` (and stale stage 3 rows are removed).

1. Blocks = `entities.blocks.plan_blocks` (same sections, splitting, context lines, TOC and page
   numbers left out), `ACTIVITY_BLOCK_MAX_CHARS` (12000). One request per block, sequentially.
2. The model sees the rules (`prompt.py`), the document card, the registry as `E<entity_id> |
   name | тип | также | родитель | роли` and the block. It answers **provisions** `{type,
   type_unclear, formulation, specificity specific|generalized|needs_clarification, condition,
   deadline, periodicity, participation individual|each|joint|alternative|unclear,
   participant_designation, participants[], sources[], notes[]}`; a participant is `{entity:
   "E<n>" | null, designation, group, condition, note, sources[]}`; a source is `{node_id, quote,
   supports[]}`.
3. `verify.py` checks every answer and **expands each provision into one record per
   participant** (one record = one entity; identical wording at different entities stays
   separate): node ids and quotes of this document (`SourceVerifier`, quotes must contain words),
   registry keys, supports for formulation, type, every filled condition/deadline/periodicity,
   non-individual participation and non-specific specificity; `entity` support per participant,
   `membership` support when included through a `group`; designation + note for `entity: null`
   (unresolved role or undisclosed group remainder); individual = 1 participant, each/joint/
   alternative ≥ 2; the formulation must rest on a non-context line of the block. Each record gets
   the shared sources plus its participant's own, the provision condition joined with the
   participant's condition, and `participant_entity_ids` = the other known participants. Errors
   go back to the model (`ACTIVITY_RETRIES`, default 2); the best attempt keeps only provisions
   that passed. A model error or exhausted retries ⇒ block `failed` (never `none`) + blocking
   `block_failed` issue.
4. `checks.py`: a record is `needs_review` with an unresolved participant (`unresolved_entity`),
   unclear participation, unclear type, specificity `needs_clarification` or a model note,
   otherwise `checked`. Document: `done`, or `needs_review` with failed/unclear blocks or stored
   records needing review. A crash ⇒ `failed` + blocking issue.
5. `store.py` — re-runs replace, not add (methodology §6), in one transaction: a block's verified
   result replaces the block's previous records; records matching by `block_node_id + entity_id +
   record_type + normalised formulation` keep their ids, unmatched previous records are deleted.
   A failed block keeps its previous records and gets a `block_failed` issue saying the update
   failed. Records of blocks no longer planned are deleted; block marks and block issues describe
   the latest run.

Tables: `activity_records` (`block_node_id`, `entity_id` NULL ⇒ `note` required, `designation`,
`participation`, `participant_designation`, `participant_entity_ids` JSON, `specificity`, …),
`activity_sources` (per record), `activity_blocks`, `activity_issues`, column
`documents.activities_status`; composite `(document_id, id)` keys keep everything in one document.

Endpoints: `GET /api/documents/{id}/activities` (flat records with entity name, participation,
other participants with names, sources `{node_id, path, location, quote, start, end, supports}`),
`GET /api/documents/{id}/activity-report` (status, record count, block marks, issues),
`POST /api/documents/{id}/activities` → 202, re-runs stage 3 and later stages (503 without a model).

### 8. Function collisions (4.1)

`src/la_rp_peace/collisions/`: `CollisionStage` (`name = "collisions"`) runs after activities when
both `entities_status` and `activities_status` are `done`/`needs_review` (otherwise
`collisions_status = not_started`, stale 4.1 rows removed). It is chained only when
`OPENAI_API_KEY` is set (it needs `OPENAI_EMBEDDING_MODEL`); retries = `ANALYSIS_RETRIES`.

1. `sides.py`: compared sides = function/duty records with a known entity (`R<id>`); records with
   participation `joint` sharing a `provision_key` become ONE consolidated view (`V<key>`, all
   participants, parents, categories, source records, conditions). `each`/`alternative`/`unclear`
   are never consolidated. Goals, tasks, rights, prohibitions of the same entities are context only.
2. `pairs.py`: local basis = two different participants that are children of the same resolved
   parent (any categories); category basis = two different participants of one category
   (`unclear`/`other` excluded). Never paired: two records of one entity, a view with its own
   records. Unordered pairs, both bases kept with the participants that gave them. Every allowed
   pair with raw cosine STRICTLY > 0.75 is verified (no top-k, no rounding).
3. `prompt.py` + `verification.ask_in_batches` (10 per request): the methodology's instruction
   verbatim, six checks; each question has both sides, bases, similarity, stage 3 quotes with node
   paths, full texts of the cited nodes and the context records. `checks.py`: verdict, strict shape,
   sources verbatim in THIS document; explanation minus similarity phrases («тексты похожи»,
   «высокое сходство», numbers) must keep ≥ 8 words; `collision` needs a `side_a` source among side A's
   stage 3 nodes AND a `side_b` source among side B's; `no_collision` needs ≥ 1 source;
   `insufficient_data` must say what is missing. Unanswered/invalid ⇒ pair `status = error`, never a verdict.
4. `store.py`: one transaction replaces `collision_runs` (coverage per path, compared sides, model,
   metric, text format), `collision_views` + `collision_view_records`, `collision_pairs` (one row per
   pair, sides as record/view FKs, bases, similarity, verdict/explanation or error) and
   `collision_sources`; composite `(document_id, id)` keys. Status `needs_review` with errors or any
   `collision`/`insufficient_data`, else `done`; a crash ⇒ `failed`, previous result kept.

Endpoints: `GET /api/documents/{id}/collisions` (pairs grouped `collision`/`no_collision`/
`insufficient_data`/`errors`, both sides with participants, parents, formulations and stage 3 sources,
verdict sources `{node_id, path, location, quote, start, end, supports}`),
`GET /api/documents/{id}/collision-report` (status, coverage per path, pairs sent, verdict and error
counts), `POST /api/documents/{id}/collisions` → 202 (503 without a model or embeddings, 404 unknown).

### 9. Function cascade (4.2) — **done**

`src/la_rp_peace/cascade/`: `CascadeStage` (`name = "cascade"`) is the last post-parse stage
(after activities); it needs the chat model and an `Embedder` (`OpenAIEmbedder`,
`OPENAI_EMBEDDING_MODEL`, left out without `OPENAI_API_KEY`). It reads stage 2 entities and
stage 3 records **from the database only** and runs when `entities_status` and
`activities_status` are `done`/`needs_review`; otherwise `cascade_status` stays `not_started`
(stale 4.2 rows removed). `running` is committed first; a crash ⇒ `failed` (previous rows kept).

1. `groups.py` — a group = entity N + its direct children (`parent_status = resolved`,
   `parent_id = N`); parent functions = N's `task`/`function`/`duty` records, child functions =
   the children's. Records with `entity_id` NULL belong to no group (listed in the report).
   Functions of entities with an `unknown`/`ambiguous` parent ⇒ `needs_clarification` findings,
   never «no pair»; an entity ambiguous between N and others marks N's group incomplete.
2. `matching.py` — `activity_text` (`activity-v1`) embeddings, cached; cosine of every child
   function with ALL parent functions of its group, raw maximum (no rounding). Exact tie at the
   top ⇒ `ambiguous` with all tied ids, no LLM. `> 0.85` ⇒ auto; `> 0.50 and <= 0.85` ⇒ one
   question; `<= 0.50` / no candidates ⇒ no pair. Never falls back to the second best.
3. `links.py` + `prompt.py` — `verification.ask_in_batches` (10 per request): question id
   `q<child_record_id>`, both records with entity, type, formulation, conditions, participation,
   specificity, the similarity and verbatim stage 3 quotes with node ids/paths. Answer
   `{"answers":[{"question_id","verdict":"confirmed|rejected","explanation"?}]}`; nothing else is
   accepted. No valid answer ⇒ link `error`; not asked ⇒ `pending`; neither is a rejection.
4. `findings.py` — one set of links, two checks. Child without accepted parent ⇒ «Основание не
   найдено» (`not_found`/`not_confirmed` final; `ambiguous`/`pending`/`error`/`no_parent_functions`
   not final). Parent function of a group without accepted child ⇒ «Исполнитель не найден»
   (`no_accepted_child` final; `pending` while an unresolved link could still attach a child,
   `group_incomplete`, `no_child_functions` not final). Top objects need no parent, leaves need no
   children. **Not detected in v1:** the §6 exemption «действие закреплено лично за текущим
   уровнем» — such functions appear as «Исполнитель не найден» with a «требует проверки» note.
5. `store.py` — one transaction replaces all 4.2 rows of the document. Status `needs_review` when
   any finding exists, else `done`.

Tables: `cascade_groups` (entity, child entity ids, parent/child record ids, uncertain entity ids),
`cascade_links` (one per child function: best candidate, raw `best_similarity`, `decision
auto|llm|none`, `verdict`, `explanation`, `status accepted|not_found|not_confirmed|ambiguous|
pending|error`, `error`, `attempts`, `tied_record_ids`, `embedding_model`, `metric`,
`text_format`), `cascade_findings` (`kind`, `reason`, `final`, record, entity, group, link,
message); composite `(document_id, …)` keys keep everything in one document.

Endpoints: `GET /api/documents/{id}/cascade` (groups with entities, functions + sources, links;
chains «задача → функция → действие» from accepted links; findings with label, entity and record),
`GET /api/documents/{id}/cascade-report` (counts by decision/verdict/status/kind/reason, final
anomalies, excluded record ids), `POST /api/documents/{id}/cascade` → 202, re-runs stage 4.2
(503 without a model or embedder).

## Not doing

Auth, multi-tenancy, migrations, OCR, background workers outside the API process,
.doc/.xls conversion.
