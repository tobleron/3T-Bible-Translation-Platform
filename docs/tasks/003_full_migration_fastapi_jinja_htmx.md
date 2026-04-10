# 003 Full Migration to FastAPI + Jinja2 + HTMX

## Objective

Replace the current terminal-first editorial workbench with a local browser-based app that preserves the existing Python workflow, keeps EPUB generation local, and gives a clearer editing and review surface.

## Target Stack

- Backend: FastAPI
- Templating: Jinja2
- Interactivity: HTMX
- Optional light client behavior: Alpine.js only where HTMX is not enough
- Styling: plain CSS first; Tailwind only if it materially speeds layout work

## Scope

- Keep the app local-first and single-user
- Preserve the current Python services for analysis, state handling, JSON commit, and EPUB generation where possible
- Replace the terminal/Textual workflow with browser views and HTTP endpoints
- Support chapter/chunk selection, study view, drafting, review, commit preview, and EPUB generation
- Keep file-based project data and output paths intact during the first migration pass

## Deliverables

1. A FastAPI app entrypoint that runs the local workbench in a browser
2. A base HTML layout with clear workspace regions for navigation, source material, draft editing, and job/output feedback
3. Routes and templates for:
   - home
   - session/chapter selection
   - chunk selection
   - study view
   - drafting/chat workspace
   - review/commit preview
   - EPUB generation status
4. Background job handling for long-running model and EPUB tasks
5. Reuse or extraction of existing domain logic into importable service modules
6. A replacement launcher command in `ttt.sh`
7. Smoke tests for the core browser workflow

## Constraints

- Do not break existing JSON formats or EPUB output contracts during migration
- Do not require a public deployment target
- Prefer incremental migration over a big-bang rewrite
- Avoid introducing a heavy SPA frontend unless later requirements force it

## Migration Plan

1. Extract terminal-independent workflow logic from the current workbench into reusable Python services
2. Create the FastAPI app skeleton, template structure, static assets, and local launcher
3. Implement read-only workflow pages first: home, chapter selection, chunk selection, study
4. Implement editing and review flows with autosave or explicit stage actions
5. Add background execution and status polling for analysis and EPUB jobs
6. Port commit, validation, and preview actions
7. Add smoke tests and remove or retire obsolete terminal-only UI paths

## Acceptance Criteria

- The local user can complete the normal passage workflow entirely in the browser
- Source material and draft text are easier to read than in the terminal UI
- EPUB generation can still be triggered from the app and uses committed JSON on disk
- Existing project data remains usable without manual conversion
- The new launcher is reliable on the current local machine setup

## Notes

This task covers the migration foundation only. Follow-up tasks can break the work into routes, templates, job orchestration, editor UX, and test coverage once implementation starts.
