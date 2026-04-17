# CSS Split Plan

The app currently ships `../app.css` as one stylesheet to avoid a build step.

`../app.css` is organized as feature sections. Keep new rules inside the closest feature section and avoid scattering a component across unrelated areas.

## Current Section Map

1. Theme tokens and reset.
2. Topbar, settings dialog, and shared primitives.
3. Workspace layout, navigation, editor, study context, and JSON browser.
4. Chat, streaming markdown, prompt engineering, and support notes.
5. Commit, EPUB, jobs, and responsive states.

## Future Split Order

When CSS is split, keep plain linked stylesheets in this order:

1. `base.css`
2. `layout.css`
3. `workspace.css`
4. `editor.css`
5. `context_panel.css`
6. `chat.css`
7. `support.css`
8. `settings.css`
9. `epub.css`

Suggested ownership:

- `base.css`: tokens, reset, typography, shared buttons, badges, flash states.
- `layout.css`: topbar, page shell, home/dashboard, workspace columns, navigation.
- `workspace.css`: workspace cards, chunk banners, merge bar, JSON browser, shared workspace feedback.
- `editor.css`: verse editor, review rows, editor modes, commit/revision controls.
- `context_panel.css`: study toolbar, study blocks, lexical details, translation/source rows, gloss tooltip.
- `chat.css`: chat toolbar, sessions, message log, streaming output, markdown, thinking blocks.
- `support.css`: justification notes, footnotes, inline formatting, prompt engineering.
- `settings.css`: settings dialog and endpoint form states.
- `epub.css`: EPUB generation, job status, download/history surfaces.

Do not introduce a frontend build pipeline unless the UI migrates to a full client-side application.
