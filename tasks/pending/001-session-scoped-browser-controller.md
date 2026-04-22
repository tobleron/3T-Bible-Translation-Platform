# Session-Scoped Browser Controller

Severity: critical

Evidence: `ttt_workbench.webapp` uses one module-level `_CONTROLLER`; Chainlit imports and mutates the same controller.

Implementation steps:
- Introduce explicit browser/workspace session ownership for mutable state.
- Keep repositories and static data shared, but move `SessionState`, chat sessions, flash messages, editor state, and selected sources behind a session lookup.
- Update FastAPI and Chainlit entrypoints to resolve the same session id.

Acceptance criteria:
- Two browser sessions can open different chunks without affecting each other.
- Chainlit chat for one session does not change another session's current chunk.

Tests:
- Add multi-session route tests and Chainlit/controller isolation tests.
