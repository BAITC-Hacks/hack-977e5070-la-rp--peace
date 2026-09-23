# Sula: web app and hackathon demo handoff

**Decision: deliver the frontend as a browser-based web application.** Use the
existing SvelteKit/Svelte 5 UI and connect it to the Python backend. For the
hackathon, demonstrate the app in Chrome or Edge on the presentation laptop.

This note records the requested delivery format and demo priorities. The detailed
frontend specification remains in [`.agents/frontend.md`](../.agents/frontend.md).
Coordinate the actual API with Alim and the analysis outputs with Marinadec.

## Delivery and startup

- Run the web app locally for the demo. Public hosting is optional unless the
  organizers separately require an accessible URL. Desktop/mobile packaging is
  outside this delivery scope.
- The simplest initial setup is two processes: the Svelte frontend and FastAPI.
  The audience sees one browser tab. The current development configuration uses
  the frontend at `http://localhost:5173` and the API at `http://localhost:8000`.
- Document the exact frontend startup/build commands, backend URL configuration,
  and required setup. Backend startup and model settings are in the
  [root README](../README.md). Model credentials stay in the backend.
- Local hosting still requires internet access for the configured remote model.
  Display backend/model errors clearly and preserve the user's selected files
  where possible.
- Once integration is stable, serving the built UI from FastAPI is an optional
  packaging improvement. Agree that work with Alim; include a SPA fallback for
  direct navigation and refresh, while preserving API and asset error responses.
  Two working processes are sufficient for the presentation.

## Immediate scope: integrate the current stages

Stage 1 parsing is being implemented by Claude/Alim; Marinadec is developing the
next structuring stage. Connect the UI to the real outputs as they become available.

1. Upload documents into clearly labeled **«До»** and **«После»** sets.
2. Show the actual processing status, errors, and available parsing warnings.
3. Let the user inspect the document structure and extracted metadata supplied by
   the backend, then open the corresponding source fragment and original file.
4. Integrate Marinadec's structured output once its API shape is agreed and exposed.

Treat unavailable analysis stages as unavailable. Do not populate findings with
invented results or build a substitute backend. Report endpoint/contract blockers
to the relevant owner. This checkpoint demonstrates parsing and traceability;
it does not claim that organizational comparison is already implemented.

Registered uploads survive a refresh in the same tab: the frontend stores document
references in `sessionStorage`, scoped to the backend URL, then fetches their current
status and resumes polling. Files whose upload was not acknowledged must be selected
again; file contents are not stored in the browser. A Word comparison is unavailable
when either document has blocking parsing issues; its error links to the documents.

## Final results flow, when comparison stages are available

The tech task's §7 requires visible results for unit changes, function comparison
and potential losses, duplication and potential conflicts of interest, supporting
sources, and an understandable analytical conclusion.

Present those results in compact tables/cards with filters. Prioritize opening a
finding's exact supporting passages, including both document versions where
relevant. Show uncertainty and the advisory nature of AI findings. The source
panel should expose the document name, clause/location, quote, and surrounding
context. Keep unknown locations unknown.

Use Russian labels. Ensure the upload, results tables, and source panel remain
readable on a projector at 1024–1280 px width. Follow the existing frontend spec
for keyboard access and loading/error states. Advanced graph views, history,
benchmarking, and multiple export formats follow the working core.

## Demo acceptance and rehearsal

- Current checkpoint: upload a real document, show processing and its parsed
  structure, then open a source fragment in context.
- Final demo: upload before/after documents, inspect known changes from the control
  set, open their evidence, and show the analytical conclusion. Rehearse this
  end-to-end flow once the required stages are implemented.
- Check that refreshing the displayed route works and that original-file links
  and source navigation work through the real backend.
- Prepare a genuine saved run and a short recording once available. Clearly label
  a saved run when using it during model latency or connectivity problems.
- Include reproducible startup instructions and a brief architecture description;
  these are deliverables in task §10. The supplied task does not require a public
  deployment or installer.

Technical references: [SvelteKit SPA deployment](https://svelte.dev/docs/kit/single-page-apps)
and [FastAPI static files](https://fastapi.tiangolo.com/tutorial/static-files/).
