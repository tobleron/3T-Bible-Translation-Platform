# 019 Split CSS by Feature

## Default Choice

Keep `app.css` as the shipping stylesheet for now, then split by feature without introducing a CSS build step.

## Objective

Improve maintainability and reduce style regressions.

## Acceptance Criteria

- CSS sections are identified by feature.
- Future files can be split into layout, editor, context panel, chat, support, settings, and EPUB styles.
- No frontend build pipeline is required.

