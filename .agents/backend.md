# Backend Spec

**Owner:** Alim (backend, DB). **Methodology:** Marinadec — *how* units and functions are
compared is theirs (`docs/methodology/`, `src/la_rp_peace/analysis/`). The backend owns
everything around it: ingestion, storage, the HTTP API, running analyses, and serving results.
Source of truth: the organiser's tech task (docx in the repo root). API contract shared with
the frontend: [`frontend.md`](frontend.md) §4.

## Stack

| Concern | Choice | Why |
|---|---|---|
| API | FastAPI + uvicorn, sync endpoints | Typed, OpenAPI at `/docs` for Sula for free |
| DB | PostgreSQL 16 (`compose.yaml`), SQLAlchemy 2 sync ORM, psycopg 3 | One `docker compose up`; no async ORM overhead |
| Schema | `Base.metadata.create_all()` on startup — **no migrations** | Six hours. Schema change → `docker compose down -v` |
| Files | Original bytes stored in Postgres (`documents.content`, deferred) | No volume/path management; files are ~100 KB |
| Parsing | python-docx, pymupdf, openpyxl | .docx / .pdf / .xlsx from the task (§5) |
| Jobs | In-process `ThreadPoolExecutor(max_workers=1)` — no Celery/Redis | One demo user; one moving part less |
| Tests | pytest on in-memory SQLite (models use portable types only) | Suite runs without Docker |

Run:

```bash
docker compose up -d db
uv run uvicorn la_rp_peace.api.app:create_app --factory --reload   # http://localhost:8000/docs
```

Config (env or `.env`, see `.env.example`): `DATABASE_URL`, `MAX_UPLOAD_MB`, `CORS_ORIGINS`, `LOG_LEVEL`.

## Layout

```
src/la_rp_peace/
  config.py, db.py, models.py, enums.py
  ingestion/     format parsers → clause tree (numbering.py), classify.py, service.py
  api/           app.py (factory), deps.py, schemas.py, documents.py
  analysis/      Marinadec — comparison stages (not yet present)
```

## Slices

### 1. Ingestion + document API — **done**

Every upload is parsed into a **clause tree**: each clause has a stable id, dotted `number`,
human citation `anchor` (`п. 5.3.2 «а»`, `разд. 10`, `лист «Оргструктура», стр. 3`), text,
parent, and location (paragraph index / page / sheet+row). This is what every finding cites
(§7.4, §9 — no claim without a source).

Handled in real documents (`test_data/`): literal-text numbering, clauses glued into the previous
paragraph (split only when the number is a valid successor, so «п.11 Положения» stays intact),
letter/dash sub-items, unnumbered headings, table of contents skipped, merged table cells.
`.doc`/`.xls` → 415 with «пересохраните как .docx/.xlsx». Scanned PDF without text → 422.
Document type is guessed from title/filename (`classify.py`) and can be overridden (PATCH).

Endpoints: `POST/GET /api/documents`, `GET/PATCH/DELETE /api/documents/{id}`,
`GET /api/documents/{id}/clauses`, `GET /api/documents/{id}/file`, `GET /api/health`.

### 2. Analyses and live progress

- Tables: `analyses` (name, status `queued|running|done|failed|cancelled`, document ids, error,
  timestamps), `analysis_stages` (name, order, status), `analysis_events` (log lines for SSE replay).
- `POST /api/analyses` → queue on the executor; `GET /api/analyses`, `GET /api/analyses/{id}`,
  `POST …/cancel` (cooperative flag checked between stages), `DELETE`.
- `GET /api/analyses/{id}/events` — SSE (`stage`, `log`, `done`, `error`) via `StreamingResponse`;
  replays stored events first so a reconnecting browser misses nothing.

### 3. Seam for the methodology (agree with Marinadec before coding)

Backend calls an ordered list of stages from `la_rp_peace.analysis`; each stage receives the
analysis context (documents + clause trees + earlier stage outputs + a `report(message)` callback
for the live log) and returns typed results. Findings must carry `SourceRef`s = clause id +
quoted span, never free text. Stage names map 1:1 to the frontend stepper (frontend.md §2.2).
LLM provider, prompts and keys are a methodology decision; backend only provides a config slot.

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
