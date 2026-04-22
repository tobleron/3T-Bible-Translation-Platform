# Accurate Project Progress

Severity: medium

Evidence: project summary counts chapter file existence as translated progress.

Implementation steps:
- Count total verses and non-empty committed verses.
- Derive chapter/chunk completion from actual verse content.
- Cache summary and invalidate on commits.

Acceptance criteria:
- Empty scaffolded chapters do not count as translated.

Tests:
- Add progress tests for empty, partial, and complete chapters.
