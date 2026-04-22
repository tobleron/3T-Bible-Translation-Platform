# Core Invariant Test Suite

Severity: high

Evidence: current tests pass but focus mainly on smoke/regression behavior, not state corruption or security invariants.

Implementation steps:
- Add tests for session isolation, atomic persistence, commit rollback, autosave ordering, XSS escaping, provider failures, and chunk identity.

Acceptance criteria:
- High-risk invariants are covered by focused tests.

Tests:
- This task is the test expansion itself.
