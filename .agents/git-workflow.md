# Git Workflow

Team of three, one hackathon repo, one shared `main`. The goal of this document is that
nobody ever loses work and nobody spends hackathon time untangling history.

Read this together with [`guidelines.md`](guidelines.md), which defines the commit
message and branch naming conventions this file assumes.

## The five rules

1. **Never force-push `main`.** Not with `--force`, not with `--force-with-lease`.
2. **Never commit directly on `main`.** Branch, then merge.
3. **Rebase onto `origin/main` before you open or merge a PR.** Conflicts are yours to
   resolve on your branch, not everyone's to discover on `main`.
4. **Push at least once an hour.** Unpushed work is invisible to the other two, and
   invisible work is work that gets duplicated.
5. **One task, one branch, one day maximum.** Long-lived branches are what make
   conflicts hard.

## Why rule 1 exists

This already happened here. `main` was force-pushed early on: commit `7019dbb`
("Add LABUBU heading to README") was rewritten into `1ce34ca`. Anyone who had already
pulled `7019dbb` ended up with a local `main` pointing at a commit that no longer
existed upstream, diverged from the real `main`, and every later push from that clone
was rejected. It cost a rebase and a conflict resolution to recover.

Force-pushing a shared branch does not just change history — it silently invalidates
every teammate's clone. If you think you need it, ask in the team chat first.

## Branch model

```
main                 always green, always deployable, protected by convention
 ├── feat/<thing>    new functionality
 ├── fix/<thing>     bug fixes
 ├── chore/<thing>   tooling, deps, CI
 └── docs/<thing>    documentation only
```

**Name branches after the work, not after yourself.** This repo currently has a branch
called `Sula`, stale since its author moved on. Nobody else can tell what is in it, or
whether it is safe to delete. `feat/lead-scoring` answers both questions instantly.

Delete your branch after it merges. GitHub offers a button for this; use it.

## Daily loop

Set this once per clone so pulls never create surprise merge commits:

```bash
git config pull.rebase true
```

Then, per task:

```bash
# 1. Start from current main
git checkout main
git pull                       # rebases, per the config above

# 2. Branch for the task
git checkout -b feat/short-description

# 3. Work. Commit in small, complete steps.
uv run ruff format .
uv run ruff check --fix .
git add <specific files>       # never `git add -A`
git commit -m "feat: add lead scoring endpoint"

# 4. Before pushing, catch up with main
git fetch origin
git rebase origin/main         # resolve conflicts here, on your own branch

# 5. Push and open a PR
git push -u origin feat/short-description
gh pr create --fill
```

Rebasing **your own unmerged branch** is safe and expected — that is not what rule 1
forbids. Rule 1 is about `main` and any branch someone else has based work on.

## Reviews

Three people, so: **one approval merges.** Do not wait for both others.

Keep PRs small enough to review in five minutes. A PR that touches 40 files will not get
a real review during a hackathon — it will get a rubber stamp, which is worse than no
review at all.

Squash-merge so `main` stays one commit per logical change:

```bash
gh pr merge --squash --delete-branch
```

The squash commit message must still follow Conventional Commits.

## Staying out of each other's way

Most conflicts are an organisational problem, not a git problem.

**Split by file, not by layer.** If two people both "work on the API", they will both
edit the same router file. Agree on module ownership at the start of each session and
write it in the team chat: one person owns ingestion, one owns scoring, one owns the
API surface.

**Shared files need a heads-up.** In this repo those are `README.md`, `pyproject.toml`,
`uv.lock`, and anything in `.agents/`. Say in chat before you touch one. `README.md`
has already conflicted once, because two people appended to the end of the same file.

**Append in your own section.** When several people must edit one document, give each
section a single owner rather than all editing the bottom of the file.

## Resolving conflicts

**`uv.lock` — never hand-edit, never hand-merge.** It is generated. Take either side
wholesale and regenerate:

```bash
git checkout --theirs uv.lock   # or --ours; the choice does not matter
uv lock                         # regenerate from pyproject.toml
git add uv.lock
```

**`pyproject.toml` — almost always "keep both".** Two people adding two different
dependencies is not a real conflict; merge both lines, then run `uv lock`.

**Source files — resolve, then re-run the checks.** A resolved conflict that no longer
compiles is a broken `main`:

```bash
uv run ruff check .
uv run pytest
```

**If a rebase goes wrong, you can always back out:**

```bash
git rebase --abort
```

And if you have already lost a commit, it is almost certainly still there:

```bash
git reflog                      # find the hash
git branch recovered <hash>
```

## Merge checklist

Before you merge to `main`:

- [ ] Rebased onto current `origin/main`
- [ ] `uv run ruff format --check .` passes
- [ ] `uv run ruff check .` passes
- [ ] `uv run mypy .` passes *(will pass once the first module exists)*
- [ ] `uv run pytest` passes *(will pass once the first test exists)*
- [ ] Commit messages follow Conventional Commits
- [ ] One teammate approved
- [ ] Branch deleted after merge
