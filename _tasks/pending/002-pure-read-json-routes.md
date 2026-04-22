# Pure Read JSON Routes

Severity: high

Evidence: JSON tree/preview routes call `select_chapter()` or `open_or_select_chunk()`.

Implementation steps:
- Split route-parameter payload building from active workspace mutation.
- Make JSON tree, JSON chapter, and preview endpoints pure reads.

Acceptance criteria:
- Calling JSON endpoints does not alter `SessionState.book`, `chapter`, or chunk range.

Tests:
- Add regression tests that set one active chunk, call JSON routes for another chunk, and assert active state is unchanged.
