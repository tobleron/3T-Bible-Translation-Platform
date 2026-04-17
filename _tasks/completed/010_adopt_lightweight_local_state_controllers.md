# 010 Adopt Lightweight Local State Controllers

## Default Choice

Use lightweight local JavaScript controllers with the already-loaded Alpine.js available for markup-level state. Do not add a bundler yet.

## Objective

Handle tabs, modals, button states, toasts, and panel-local UI state without unnecessary server trips.

## Acceptance Criteria

- Shared workspace UI behavior lives in static JavaScript.
- The app still works with server-rendered Jinja partials.
- No Vite/Webpack/React build step is required.

