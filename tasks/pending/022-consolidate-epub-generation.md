# Consolidate EPUB Generation

Severity: medium

Evidence: browser routes and TUI command duplicate EPUB subprocess generation.

Implementation steps:
- Create a single EPUB build service.
- Use it from sync browser route, download route, background job, and TUI command.
- Normalize error/output handling.

Acceptance criteria:
- All EPUB entrypoints share one implementation.

Tests:
- Add service tests and route tests for success/failure.
