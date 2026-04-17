# 009 Keep HTMX/Jinja and Avoid Premature React Migration

## Default Choice

Keep FastAPI + Jinja + HTMX as the primary UI architecture. Do not introduce React unless the editor becomes a full client-side application.

## Objective

Improve responsiveness inside the current server-rendered architecture before adding a build-heavy frontend stack.

## Acceptance Criteria

- Architecture docs clearly prefer HTMX/Jinja for the current app.
- React is documented as a later option only for a full SPA/editor migration.
- Current fixes focus on swaps, request state, modular JavaScript, and background jobs.

