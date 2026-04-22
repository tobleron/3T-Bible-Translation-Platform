# Server-Side Chat Context API

Severity: high

Evidence: prompt engineering injects context by reaching into the Chainlit iframe DOM.

Implementation steps:
- Persist selected prompt/context settings per chat session.
- Assemble context server-side before sending model messages.
- Keep copy/inject as optional convenience, not the core integration.

Acceptance criteria:
- Chat includes selected context without iframe DOM manipulation.

Tests:
- Add tests for context selection persistence and Chainlit message assembly.
