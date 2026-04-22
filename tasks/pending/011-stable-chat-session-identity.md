# Stable Chat Session Identity

Severity: high

Evidence: chat session key includes a title-derived chunk hash.

Implementation steps:
- Make session identity based on testament/book/chapter/range plus stable catalog id if present.
- Store title as mutable metadata.
- Migrate old title-hash sessions.

Acceptance criteria:
- Renaming a chunk/title does not hide prior chat sessions.

Tests:
- Add migration and title-change preservation tests.
