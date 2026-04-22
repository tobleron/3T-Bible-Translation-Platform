# Autosave Revision Control

Severity: high

Evidence: autosave aborts prior browser fetches but server writes are unconditional.

Implementation steps:
- Add editor revision ids to autosave requests/responses.
- Reject stale writes server-side.
- Surface conflict feedback in the editor.

Acceptance criteria:
- Out-of-order autosaves cannot overwrite newer text.

Tests:
- Add stale autosave and multi-tab conflict tests.
