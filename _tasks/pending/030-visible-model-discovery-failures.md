# Visible Model Discovery Failures

Severity: medium

Evidence: `list_models()` silently returns `llama.cpp-model` on discovery failures.

Implementation steps:
- Track discovery status and last error separately from model options.
- Surface fallback state in settings/chat UI.

Acceptance criteria:
- Unreachable endpoint produces a visible warning instead of a silent fake model list.

Tests:
- Add model discovery failure tests.
