# Remove Or Restore SSE Chat

Severity: high

Evidence: old `chat-stream-form` JavaScript remains, but the active UI is a Chainlit iframe and no live `/chat/stream` route exists.

Implementation steps:
- Decide one active chat implementation.
- If Chainlit remains primary, remove old SSE template/static code and dead tests.
- If custom SSE is restored, add a real route and production DOM tests.

Acceptance criteria:
- Tests exercise the production chat path, not injected dead DOM.

Tests:
- Update Playwright coverage around actual chat UI behavior.
