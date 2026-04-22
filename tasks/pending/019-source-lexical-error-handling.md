# Source And Lexical Error Handling

Severity: medium

Evidence: source and lexical parsers catch the wrong exceptions and sometimes silently return empty results.

Implementation steps:
- Catch `KeyError`, `TypeError`, and `ValueError` where conversion happens.
- Distinguish missing data from query/load failures.
- Surface structured warnings.

Acceptance criteria:
- Malformed source rows do not crash, and operational DB failures are visible.

Tests:
- Add malformed source row and SQLite failure tests.
