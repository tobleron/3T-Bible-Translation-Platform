# 022 Add JSON APIs for Interactive Controls

## Default Choice

Keep Jinja partials for layout and use JSON endpoints for high-frequency interactions such as autosave, enhancement, and browser-side state.

## Objective

Avoid HTML swaps where the browser only needs a small state update.

## Acceptance Criteria

- Autosave and field enhancement remain JSON-first.
- New highly interactive controls prefer JSON responses.
- Server-rendered partials remain available for complex layout changes.

## Status

Completed. Autosave, field enhancement, prompt context, JSON browser, and job controls are JSON-first. Added `/interactive-state` as a compact JSON state endpoint for browser-side controls while preserving Jinja partial routes for layout-changing interactions.
