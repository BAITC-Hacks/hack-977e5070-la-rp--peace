# Coding Guidelines

This file provides coding and git guidelines for AI coding agents.

> **Status:** the project has no application code yet, so the toolchain-specific
> sections below are marked **TBD**. Fill them in as part of the first commit that
> introduces a stack — do not let code land while they are still placeholders.

## Mandatory Agent Rules

**This is a production-grade system, not a playground. These rules are non-negotiable.**

1. **No dull or boilerplate implementations.** Every piece of code must be purposeful,
   correct, and production-ready from the first commit. Do not write stub implementations,
   placeholder logic, TODO-only functions, or "fill this in later" scaffolding. If a
   feature cannot be fully implemented, say so explicitly and propose a plan rather than
   shipping skeleton code.

2. **Always consult this file before building anything.** Before writing any code, read
   this file in full to understand conventions, architecture constraints, and critical
   implementation notes. Code that contradicts this file will be rejected.

3. **No silent assumptions.** If a requirement is unclear, ask for clarification rather
   than guessing. Wrong guesses that reach production cost more to fix than a one-question
   pause.

4. **Correctness over cleverness.** Prefer clear, reviewable code. Avoid overly clever
   one-liners, premature abstractions, or patterns that require extensive mental overhead
   to follow.

## Language-Agnostic Conventions

These hold regardless of the stack.

**Structure:** Keep functions short and shallow — prefer small units over deep nesting.
Extract a helper before a function outgrows a single screen.

**Imports / dependencies:** All imports at the top of the file, grouped standard library
→ third-party → local, separated by blank lines. No lazy or function-level imports to
paper over cycles. A circular dependency is an architecture bug: restructure with
interfaces, extract the shared piece, or move the dependency to a lower layer.

**Typing:** Public functions carry complete type annotations. Prefer modern built-in
generic and union syntax over legacy compatibility aliases.

**Documentation:** Public classes and functions get a docstring or doc comment explaining
intent, not a restatement of the signature.

**Logging:** Use structured logging with bound context, not string interpolation into
a message. Log events as stable names with fields:

    log = get_logger(__name__).bind(entity_id=item.id)
    log.warning("missing_field", field_name="title")

**Error handling:** Never swallow an exception silently. Always log it with context:

    except SomeError as exc:
        log.warning("operation_failed", error=str(exc))

**Filesystem:** Prefer the standard library's path abstraction over manual string
manipulation of paths.

## Git

**Commits:** Conventional Commits — `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`.

**Branches:** `feat/feature-name`, `fix/bug-description`.

**Hygiene:** Stage only relevant files (never `git add -A` blindly). Do not leave
uncommitted changes after completing a task. This file itself is part of the repo and
must be committed alongside the work it governs.

## Stack-Specific Conventions — TBD

To be filled in when the project's language and toolchain are chosen. Until then, no
rule in this section may be cited as enforced.

- **Language & runtime version:** TBD
- **Formatter:** TBD
- **Linter and enabled rule set:** TBD
- **Type checker and strictness level:** TBD
- **Test framework and layout:** TBD
- **Package / workspace layout:** TBD
- **Config file holding the above:** TBD

## Validation & Git Workflow

**After every code change, before considering the task done:**

1. **Validate the project is runnable.** Run the project's format check, lint, type check,
   and test suite — zero errors on each.

   > Commands: **TBD.** Record the exact invocations here once the toolchain exists, so
   > this step is mechanically checkable rather than aspirational.

2. **Format before committing.** Run the project's auto-formatter and safe auto-fixes.

   > Commands: **TBD.**

3. **Commit and push every change:**
   - Stage only relevant files (never `git add -A` blindly)
   - Use Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`
   - Push to remote: `git push`
   - Do not leave uncommitted changes after completing a task

4. **Review after every change:**
   - Review the code diff and check that it adheres to the code style and guidelines
     of this project as described in `.agents/guidelines.md`.
   - Review relevant project docs and update them to stay accurate given the changes.

Steps 3 and 4 are **non-negotiable** and apply today. Step 1 and 2 become non-negotiable
the moment a toolchain lands — and landing that toolchain includes replacing the TBDs
above with real commands.
