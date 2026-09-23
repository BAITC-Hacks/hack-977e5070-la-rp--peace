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
```

Config (env or `.env`, see `.env.example`): `DATABASE_URL`, `MAX_UPLOAD_MB`, `CORS_ORIGINS`,
`LOG_LEVEL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`, `OPENAI_REASONING_EFFORT` (default `low`), `PROFILE_MAX_CHARS`,
`PROFILE_RETRIES`, `PARSER_WORKERS`. Without the key and model, uploads return 503.

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
    pipeline.py   register upload, background parsing, one-transaction save
  api/            app.py (factory), documents.py, sources.py, schemas.py, deps.py
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

## Not doing

Auth, multi-tenancy, migrations, OCR, background workers outside the API process,
.doc/.xls conversion.
