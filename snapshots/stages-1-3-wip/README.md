# Database checkpoint: stages 1–3 (WIP)

This is a consistent snapshot of the existing live document-processing run.
It includes the original document, parsed text, organizational entities and their sources.

**Stage 3 was still running when the snapshot was taken. There are no saved activity
records in this checkpoint.** The copied `running` status is historical: a database
snapshot does not copy the running worker or its in-memory progress.

The source database and the other agent's process were not changed.

## Contents

| Item | Captured state |
|---|---|
| Document | ID `1`, anonymized internal-audit regulation, edition 9, DOCX |
| Set | `after` |
| Stage 1 | `validated`; 539 text nodes, no parsing issues |
| Stage 2 | `done`; 46 entities, 23 relations, 243 source records |
| Stage 2 review | 5 entity issues; inspect the entity report rather than assuming there are no warnings |
| Stage 3 | `running`; 0 persisted activity records and 0 persisted activity blocks |
| Original file | Included in SQLite; SHA-256 matches the document in `test_data/` |
| Database size | 806,912 bytes |
| Capture time, hashes and all row counts | [manifest.json](manifest.json) |

- [larp.sqlite3](larp.sqlite3) — standalone SQLite database.
- [manifest.json](manifest.json) — provenance, checksum, statuses and expected counts.
- This README — restoration and verification.

The backup was made through SQLite's backup API using a read-only source connection,
so committed data in the write-ahead log is included. The snapshot uses DELETE journal
mode and does not need separate `-wal` or `-shm` files.

## Get the snapshot

This directory is versioned with the project. Obtain it from the repository's `main`
branch, then follow the restoration steps below. The database is a frozen checkpoint;
it will not receive updates from the original live run.

Do not put the working database under version control: restore a copy into `data/`,
which is already ignored by Git. Credentials and `.env` are not part of this package.

## Compatible code revision

Verified against:

```text
5ebdc53f669e40d3623d7f903eecd66c4313d14a
```

The tag `snapshot-stages-1-3-20260923` preserves that revision independently of
ongoing feature-branch work. The tag does not mean stage 3 completed in this database.

Use this revision for reproducing the captured state. The current application has no
automatic schema migrations. Work in progress after this commit introduces additional
columns/tables, and older revisions lack the stage 2–3 API. Use the tagged code rather
than assuming the latest `main` is compatible.

## Restore and inspect without model calls

These commands are for PowerShell and start from a checkout containing this snapshot.
They create a separate worktree and use port 8001, leaving your existing checkout,
database and server alone.

### 1. Create the matching checkout

```powershell
$snapshotDir = (Resolve-Path 'snapshots/stages-1-3-wip').Path
$snapshotMeta = Get-Content (Join-Path $snapshotDir 'manifest.json') -Raw | ConvertFrom-Json
git fetch origin tag $snapshotMeta.compatible_code_tag
if ($LASTEXITCODE -ne 0) { throw 'Could not fetch the compatible code tag. Stop here.' }
git worktree add --detach ../hack-stages-replica $snapshotMeta.compatible_code_commit
if ($LASTEXITCODE -ne 0) { throw 'Could not create replica worktree. Stop here.' }
Set-Location ../hack-stages-replica
uv sync --locked
```

If the tag cannot be fetched, stop and check repository access. Do not substitute
another revision without checking schema compatibility.

### 2. Verify and copy the database

```powershell
$snapshotFile = Join-Path $snapshotDir 'larp.sqlite3'
$actualHash = (Get-FileHash -LiteralPath $snapshotFile -Algorithm SHA256).Hash
if ($actualHash -ne $snapshotMeta.snapshot_sha256) { throw 'Snapshot checksum mismatch' }
New-Item -ItemType Directory -Path data -Force | Out-Null
if (Test-Path -LiteralPath data/replica.sqlite3) { throw 'Replica already exists; use a fresh worktree' }
Copy-Item -LiteralPath $snapshotFile -Destination data/replica.sqlite3
```

Always run the app against this working copy, not the committed snapshot.

### 3. Start the API for inspection

```powershell
$env:DATABASE_URL = 'sqlite:///data/replica.sqlite3'
$env:OPENAI_API_KEY = ''
$env:OPENAI_MODEL = ''
uv run uvicorn la_rp_peace.api.app:create_app --factory --port 8001
```

The empty model settings disable model calls in this terminal.
Open [Swagger UI](http://localhost:8001/docs), then inspect:

| Request | Expected result from this checkpoint |
|---|---|
| `GET /api/documents/1` | Stage 1 `validated`, stage 2 `done`, stage 3 `running` |
| `GET /api/documents/1/nodes` | 539 text nodes with paths and source positions |
| `GET /api/documents/1/entities` | 46 entities with supporting citations |
| `GET /api/documents/1/entity-relations` | 23 relationships |
| `GET /api/documents/1/entity-report` | Block outcomes and 5 issues for review |
| `GET /api/documents/1/file` | Original DOCX |
| `GET /api/documents/1/activities` | Empty list: stage 3 results were not yet saved |
| `GET /api/documents/1/activity-report` | Historical `running` flag and `record_count: 0` |

To check a source, take `node_id` and `quote` from an entity's `sources`,
then submit them to `POST /api/sources/resolve`. This verifies the quote against
stored text and does not call the model.

## How to test stages 1–3

### Offline tests: repeatable application behavior

Run from the matching checkout. The full default suite excludes `live` tests:

```bash
uv run pytest -q
```

For a focused selection:

```bash
# Stage 1: extraction, tree, metadata, HTTP API
uv run pytest -q tests/test_extract.py tests/test_tree.py tests/test_metadata.py tests/test_api.py

# Stage 2: entity pipeline and HTTP API
uv run pytest -q tests/test_entity_pipeline.py tests/test_entity_api.py

# Stage 3: activity extraction, checks and HTTP API
uv run pytest -q tests/test_activities.py tests/test_activity_checks.py tests/test_activity_api.py
```

These tests use prepared/scripted model answers. They verify processing behavior and
error handling; they do not establish the quality of live model output.
At the pinned revision, `pytest -m live` tests stage 1 only.

### Live stage 3: reuse the saved stages 1–2

1. Stop only the replica server you started above.
2. In the replica worktree, copy `.env.example` to `.env` and configure your own
   `OPENAI_API_KEY`, `OPENAI_MODEL` and any required model options.
3. Remove the temporary empty overrides from the same PowerShell session:

   ```powershell
   Remove-Item Env:OPENAI_API_KEY, Env:OPENAI_MODEL -ErrorAction SilentlyContinue
   uv run uvicorn la_rp_peace.api.app:create_app --factory --port 8001
   ```

   The `DATABASE_URL` override still points to `data/replica.sqlite3`.

4. In Swagger UI, call `POST /api/documents/1/activities` **once**. It returns HTTP
   `202` and starts stage 3 against the saved document tree and entity registry.
5. Poll `GET /api/documents/1/activity-report` until the status is `done`,
   `needs_review` or `failed`.
6. Inspect `GET /api/documents/1/activities`. Check the assigned entity, formulation,
   conditions, deadlines and exact source quotations. Review the report's issues
   even if records are present.

This makes real model calls. Starting the server alone does not resume the historical
stage-3 `running` state; the explicit POST is necessary.
A fresh model run may produce different results from another run.

### Live stages 1 → 2 → 3 from the original input

With the model configured, upload the supplied edition-9 DOCX through
`POST /api/documents` with `set=after`. Use the newly returned document ID.
The application runs parsing, entity extraction and activity extraction in order.

Inspect that document's card, `nodes`, `entity-report`, `entities`,
`activity-report` and `activities`. A successful stage 1 does not imply
that stages 2 and 3 have finished; check their statuses separately.

## Snapshot verification

Before handoff:

- SQLite `PRAGMA integrity_check`: `ok`.
- SQLite `PRAGMA foreign_key_check`: no violations.
- A restored temporary copy was opened through the API at the pinned code revision,
  with model access disabled.
- Document, nodes, entities, both stage reports and activity-list endpoints returned
  HTTP 200 with the counts above.
- Downloaded original matched its SHA-256; an entity citation resolved successfully.
- The focused stage 1–3 offline test selection above passed: **101 tests**.
  Tests ran against an isolated copy of the pinned revision, not the other agent's working files.

This verifies the saved checkpoint. It is not a claim that the live stage-3 run completed.
