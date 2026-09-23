# AGENTS.md

Hackathon repo for team **la(rp)-peace**. Python 3.12, managed with `uv`.
Three people, six hours, one repo. Several AI agents (Claude Code, Codex) may
be working at the same time — assume other people's code is changing under you.

Read these before doing anything:

| Document | What it covers |
|---|---|
| [`docs/spec/`](docs/spec/README.md) | Product spec: `tz_site.md` (features, invariants, P0–P3 priorities), `prototype.html` (mockup of the whole site), `visual_compare.html` (reworked «Изменения → Визуал» screen); README says how to use them |
| [`.agents/guidelines.md`](.agents/guidelines.md) | Coding conventions, ruff/mypy rule set, validation commands |
| [`.agents/git-workflow.md`](.agents/git-workflow.md) | Branching, PRs, conflict resolution, six-hour cadence |
| [`.agents/frontend.md`](.agents/frontend.md) | Frontend scope, UI elements, Svelte stack + Svelte MCP, API contract |
| [`.agents/backend.md`](.agents/backend.md) | Backend stack, SQLite, ingestion, slices, seam for the methodology |

## Setup

```bash
uv sync
uv run uvicorn la_rp_peace.api.app:create_app --factory --reload   # API on :8000, docs at /docs
```

Data lives in one SQLite file, `data/larp.sqlite3` (git-ignored). Parsing needs
`OPENAI_API_KEY` and `OPENAI_MODEL` in `.env`; tests run offline (`pytest -m live` calls OpenAI).

## Ownership

Only modify files inside the paths owned by the person you are working for.
Shared files need a heads-up in team chat before changing them.

| Area | Owner | Paths |
|---|---|---|
| Frontend (SvelteKit UI) | Sula | `frontend/`, `.agents/frontend.md` |
| Backend & DB | Alim | `src/la_rp_peace/` (except `analysis/`), `tests/` (except `tests/analysis/`), `.env.example`, `.agents/backend.md` |
| Methodology & analysis | Marinadec | `methodology/`, `src/la_rp_peace/analysis/`, `tests/analysis/` |
| Shared (ask first) | everyone | `pyproject.toml`, `uv.lock`, `.mcp.json`, `test_data/`, shared models/interfaces, API contract (`.agents/frontend.md` §4) |

## Non-negotiables

- **Pull before starting any task and before every commit.** On `main`: `git pull`.
  On a branch: `git fetch origin && git rebase origin/main` — plain `git pull --rebase`
  on a branch only tracks that branch, so it will NOT pick up your teammates' work.
- **Never force-push `main`**, never commit directly on it.
- **Stay in your owner's paths.** Do not "fix" or refactor code owned by someone else.
- **Never add, remove, or upgrade dependencies** without explicit approval from your human.
- **No stub or placeholder code** — if it can't be finished, say so instead.
- **If blocked on code another owner hasn't written yet, stop and report.**
  Do not write your own replacement version of it.
- **Before every commit**, all of these must pass:

  ```bash
  uv run ruff format . && uv run ruff check --fix .
  uv run mypy .
  uv run pytest -q
  ```

## Working style

- One well-scoped task per session. Finish it, commit, then stop.
- Keep commits and PRs small; merge often rather than batching.
- When done, summarize what changed and which files were touched.

Everything else is in the two documents above.
