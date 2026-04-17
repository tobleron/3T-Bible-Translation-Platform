# 012 Reduce Large HTMX Workspace Swaps

## Default Choice

Keep full `#workspace-shell` swaps for navigation and multi-panel state changes, but target smaller panels for editor-only, chat-only, and context-only actions.

## Objective

Make buttons feel faster by replacing less DOM and rebinding fewer handlers.

## Acceptance Criteria

- Existing small-panel endpoints continue returning partials.
- New interactions prefer `#editor-panel`, `#chat-panel`, or `#context-panel` where the server response supports it.
- Full workspace swaps remain available when multiple panels must be refreshed.

