# Chunk Catalog Source Of Truth

Severity: high

Evidence: chunk catalog paths ignore `paths.final_data`; book aggregate payloads can override newer chapter files; cache ignores book mtime.

Implementation steps:
- Use configured final data path.
- Define canonical precedence or prefer newest valid payload.
- Invalidate cache on both chapter and book aggregate changes.

Acceptance criteria:
- UI reflects updated chunk data after chapter or book payload changes.

Tests:
- Add config-path, stale aggregate, and cache invalidation tests.
