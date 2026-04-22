# Typed Errors And Observability

Severity: medium

Evidence: LLM failures are returned as `[ERROR]` strings and routes catch broad exceptions.

Implementation steps:
- Introduce typed application/provider errors.
- Add structured logs with request id, session id, provider/model, chunk, and duration.
- Keep user-facing errors concise.

Acceptance criteria:
- UI no longer parses provider failures from raw strings.

Tests:
- Add typed error mapping tests.
