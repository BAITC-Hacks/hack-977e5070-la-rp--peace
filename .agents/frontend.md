# Frontend Spec

**Owner:** Sula. **Path:** `frontend/`. Source of truth: the organiser's tech task
*«ИИ-агент „Анализ организационной структуры и функционала“»* (docx in the repo root).

The task explicitly requires, as a deliverable, *"an interface for uploading documents and
viewing results"* (§10). Every must-have finding (§7) has to be visible and traceable to its
source in the UI — that is what the jury checks on the control document set (§11:
reorganised unit, lost function, duplicated function, correct sources).

## 1. Stack

| Concern | Choice |
|---|---|
| Framework | SvelteKit (Svelte 5, runes: `$state`, `$derived`, `$props`, `$effect`) |
| Language | TypeScript, `strict: true` |
| Rendering | `adapter-static`, SPA mode (`ssr = false`) — the Python backend serves the API |
| Styling | Tailwind CSS |
| Package manager | `pnpm` via corepack, version pinned in `package.json` `packageManager` (lockfile committed) |
| Checks | `svelte-check`, ESLint (`eslint-plugin-svelte`), Prettier (`prettier-plugin-svelte`) |
| Tests | Vitest: logic in `.ts` modules, unit-tested in Node; components with `vitest-browser-svelte` in Chromium (what `sv` 0.17 scaffolds) |
| UI language | Russian (all visible labels); code and identifiers in English |

Scaffold with `pnpm dlx sv create frontend` (template *minimal*, TypeScript, add-ons: tailwind,
eslint, prettier, vitest). Adding further npm packages follows the same rule as Python deps:
**ask first.**

Frontend checks that must pass before every commit touching `frontend/`:

```bash
cd frontend
pnpm format && pnpm lint
pnpm check          # svelte-check, zero errors/warnings
pnpm test -- --run
```

### Svelte MCP

The official Svelte MCP server gives agents current Svelte 5 / SvelteKit docs and a
static analyser for generated components. It is registered for Claude Code in the repo's
`.mcp.json` (remote server `https://mcp.svelte.dev/mcp`). For Codex, add to
`~/.codex/config.toml`:

```toml
[mcp_servers.svelte]
command = "npx"
args = ["-y", "@sveltejs/mcp"]
```

Rules for any agent writing Svelte code in this repo:

1. Call `list-sections` first, then `get-documentation` for every section relevant to the
   task. Do not write Svelte 4 syntax (`export let`, `$:`, `on:click`, stores for local state).
2. Run `svelte-autofixer` on every component you create or edit, and repeat until it returns
   no issues or suggestions.
3. `playground-link` only when the human asks for one — never for code already in the repo.

## 2. Screens and elements

Routes:

| Route | Screen |
|---|---|
| `/` | New analysis (upload) |
| `/analyses/[id]` | Progress while running, results once done |
| `/analyses` | History of past analyses |

A global **header** holds the product name, a link to history, and a persistent
disclaimer chip: *«Выводы ИИ носят рекомендательный характер и требуют проверки
ответственным сотрудником»* (§9 — must be visible on every results screen).

### 2.1 Upload screen (`/`)

| Element | Behaviour |
|---|---|
| **Analysis name** | Text input, optional; default `Анализ от <date>`. |
| **Drop zone «До реорганизации»** | Drag-and-drop + file picker, multiple files. Accepts `.docx`, `.doc`, `.pdf`, `.xlsx`, `.xls`. Rejects others client-side with an inline message. |
| **Drop zone «После реорганизации»** | Same as above. Both zones must be non-empty to start. |
| **Drop zone «Нормативные требования»** (optional §8.1) | Collapsed by default; laws, standards, regulatory docs. |
| **Drop zone «Бенчмаркинг»** (optional §8.2) | Collapsed by default; other operators' org structures. |
| **File row** | Per file: icon by format, name, size, remove button, and a **document-type select** — `Оргструктура`, `Положение о подразделении`, `Должностная инструкция`, `Распорядительный документ`, `ВНД`, `Не определено`. Type is pre-filled from the backend's classification after upload; user can override. |
| **Upload progress** | Per-file progress bar; failed upload shows error and a retry button. |
| **«Запустить анализ» button** | Disabled until both «До» and «После» have at least one successfully uploaded file. Starts the analysis and navigates to `/analyses/[id]`. |

### 2.2 Progress view (`/analyses/[id]` while `status = running`)

Shows that this is an agent, not a black box (scored under "technical implementation").

| Element | Behaviour |
|---|---|
| **Stage stepper** | Stages from the backend, in order: parsing documents → extracting units → matching units before/after → comparing functions → detecting losses → detecting duplicates and conflicts → writing the conclusion. Each: pending / running / done / failed. |
| **Agent activity log** | Live-streamed list of agent steps (timestamp, short message, e.g. «Найдено 14 подразделений в „Оргструктура_после.xlsx“»). Auto-scrolls, can be paused. |
| **Cancel button** | Cancels the run. |
| **Failure state** | Stage marked failed, backend error message, «Повторить» button. |

Transport: Server-Sent Events on `GET /api/analyses/{id}/events`; fall back to polling
`GET /api/analyses/{id}` every 2 s if the stream drops.

### 2.3 Results view (`/analyses/[id]` when `status = done`)

Tabbed layout. Tab choice lives in the URL (`?tab=`), so a link opens the same view.

**Summary bar (above tabs, always visible)** — count cards, each clickable to its tab with
the filter applied: units *preserved / transformed / created / abolished*, *lost functions*,
*duplicated functions*, *conflicts of interest*.

#### Tab «Подразделения» — §7.1

| Element | Behaviour |
|---|---|
| **Before/after structure view** | Two side-by-side trees (org hierarchy «до» / «после»). Each unit has a status badge: `сохранено`, `преобразовано` (renamed, merged, split), `создано`, `упразднено`. Hovering or selecting a unit highlights its counterpart(s) on the other side. |
| **Unit changes table** | Alternative table view (toggle): unit before, unit after, change type, short explanation, sources. Sortable, filterable by change type. |

#### Tab «Функции» — §7.2

| Element | Behaviour |
|---|---|
| **Function mapping table** | Columns: function (before), unit (before), function (after), unit (after), status (`сохранена`, `перенесена`, `изменена`, `потеряна`, `новая`), confidence, sources. Rows with `потеряна` are visually highlighted. |
| **Filters** | Status, unit, free-text search over function text. |
| **Row detail** | Expanding a row shows the agent's reasoning for the match and all source citations. |

#### Tab «Потери функций» — §7.2

A list of lost-function cards: function text, unit it belonged to, why the agent believes it
has no counterpart after reorganisation, severity, sources.

#### Tab «Дублирование и конфликты» — §7.3

| Element | Behaviour |
|---|---|
| **Duplicate card** | The two (or more) units sharing a function, the overlapping function text from each, explanation, severity, sources for each side. |
| **Conflict-of-interest card** | Units involved, the incompatible functions (e.g. one unit both performs and controls), explanation, severity, sources. |
| **Filter** | Type (duplicate / conflict), severity, unit. |

#### Tab «Заключение» — §7.5, §8.3

| Element | Behaviour |
|---|---|
| **Conclusion text** | Rendered Markdown from the backend. Inline citation markers `[1]`, `[2]`… open the source panel. |
| **Recommendations** | Numbered list of recommendations for redistributing functions / removing overlaps, each linked to the findings it addresses. |
| **Export** | «Скачать DOCX» / «Скачать PDF» (backend-generated) and «Печать» (print stylesheet). |

#### Optional tabs (only rendered if the backend returns data)

- **«Соответствие требованиям»** (§8.1): table of function ↔ regulatory requirement, status
  `покрыто / не покрыто / частично`, sources from both sides.
- **«Бенчмаркинг»** (§8.2): our transformed/created department next to comparable
  structures of other operators, with differences listed.

### 2.4 Source panel — §7.4, §9 (critical)

Every finding in every tab carries one or more **source chips** (`Положение ОТД-5, п. 3.2`).
Clicking a chip opens a right-hand side panel:

| Element | Behaviour |
|---|---|
| **Document header** | Document name, type, «до» / «после», link to download the original. |
| **Location** | Section / clause number, page (PDF), sheet and row (Excel). |
| **Quoted fragment** | The exact text the finding relies on, with the relevant span highlighted, plus a few lines of surrounding context. |
| **Navigation** | Prev / next when a finding has several sources; Esc closes. |

A finding **without** a source must never be shown as a fact: render it with a
«Нет подтверждения в документах» warning style. (The backend should not produce these; the UI
must not hide them if it does.)

### 2.5 Reviewer verdicts — §9

Each finding (unit change, lost function, duplicate, conflict) has **«Подтвердить» /
«Отклонить»** buttons and an optional comment. Verdicts are sent to the backend, shown as a
badge on the finding, and counted in the summary bar (`проверено 7 из 23`). Exports include the
verdicts.

### 2.6 History (`/analyses`)

Table of analyses: name, created at, status, counts of findings, link to open. Delete button
with confirmation.

### 2.7 Cross-cutting

- Loading skeletons for every async view; empty states for every list («Дублирований не
  найдено»).
- Error toasts for failed requests, with the backend error message.
- Works at 1280 px width and up; must not break on a projector at 1024 px (demo).
- Keyboard accessible: tabs, table rows, source chips and the side panel are reachable and
  operable without a mouse.

## 3. Suggested structure

```
frontend/src/
  lib/api/client.ts        fetch wrappers + SSE subscription
  lib/api/types.ts         TS mirror of the contract in §4 (shared interface)
  lib/components/          UploadZone, FileRow, StageStepper, AgentLog, SummaryBar,
                           OrgTreeCompare, FunctionTable, FindingCard, SourceChip,
                           SourcePanel, VerdictControls, ConclusionView
  routes/+page.svelte                 upload
  routes/analyses/+page.svelte        history
  routes/analyses/[id]/+page.svelte   progress / results
```

## 4. API contract (proposed — agree with the backend owner before building on it)

This section is a **shared interface**. Changes need a heads-up in team chat. The backend is
the source of truth for the models; `frontend/src/lib/api/types.ts` mirrors them.
Until the backend exposes an endpoint, the corresponding UI is blocked — do not build a mock
backend in `frontend/` (see *Non-negotiables* in `AGENTS.md`); report the block instead.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/documents` | Multipart upload of one file with `set` = `before` / `after` / `regulatory` / `benchmark`. Returns `Document`. |
| `PATCH` | `/api/documents/{id}` | Override `doc_type`. |
| `DELETE` | `/api/documents/{id}` | Remove an uploaded file. |
| `GET` | `/api/documents/{id}/file` | Download the original. |
| `POST` | `/api/analyses` | `{name, document_ids}` → `Analysis` (starts the run). |
| `GET` | `/api/analyses` | History list. |
| `GET` | `/api/analyses/{id}` | `Analysis` with `stages` and, when done, `result`. |
| `GET` | `/api/analyses/{id}/events` | SSE: `stage`, `log`, `done`, `error` events. |
| `POST` | `/api/analyses/{id}/cancel` | Cancel a run. |
| `PUT` | `/api/analyses/{id}/findings/{finding_id}/verdict` | `{verdict: "confirmed" \| "rejected", comment}`. |
| `GET` | `/api/analyses/{id}/export?format=docx\|pdf` | Download the conclusion. |
| `DELETE` | `/api/analyses/{id}` | Delete from history. |

Core result shapes (TypeScript notation):

```ts
type SourceRef = {
  document_id: string; document_name: string; set: "before" | "after" | "regulatory" | "benchmark";
  clause: string | null;          // "п. 3.2"
  page: number | null; sheet: string | null; row: number | null;
  quote: string;                   // exact fragment
  context: string;                 // surrounding text containing `quote`
};

type Verdict = { verdict: "confirmed" | "rejected"; comment: string | null } | null;

type UnitChange = {
  id: string; change: "preserved" | "transformed" | "created" | "abolished";
  before_unit_ids: string[]; after_unit_ids: string[];
  explanation: string; sources: SourceRef[]; verdict: Verdict;
};

type FunctionMatch = {
  id: string; status: "preserved" | "moved" | "modified" | "lost" | "new";
  before: { unit_id: string; text: string } | null;
  after: { unit_id: string; text: string } | null;
  confidence: number; reasoning: string; sources: SourceRef[]; verdict: Verdict;
};

type Overlap = {
  id: string; kind: "duplicate" | "conflict_of_interest"; severity: "low" | "medium" | "high";
  units: { unit_id: string; function_text: string }[];
  explanation: string; sources: SourceRef[]; verdict: Verdict;
};

type Unit = { id: string; name: string; parent_id: string | null; side: "before" | "after" };

type AnalysisResult = {
  units: Unit[];
  unit_changes: UnitChange[];
  function_matches: FunctionMatch[];
  overlaps: Overlap[];
  conclusion_markdown: string;           // citations as [n] → citations[n-1]
  citations: SourceRef[];
  recommendations: { text: string; finding_ids: string[] }[];
  compliance: unknown[] | null;          // optional §8.1, shape TBD with backend
  benchmark: unknown[] | null;           // optional §8.2, shape TBD with backend
};
```

## 5. Priorities (six-hour budget)

1. Upload screen + start analysis.
2. Results: summary bar, «Подразделения» (table view), «Функции», «Потери», «Дублирование и
   конфликты», source panel. **This is the demo** (§11).
3. «Заключение» tab with citations.
4. Progress view with stage stepper and agent log.
5. Before/after tree view, reviewer verdicts, export.
6. History, optional compliance/benchmark tabs.
