# Corpus-Aware Lexical Codes

Severity: medium

Evidence: lexical availability methods use `book_ref_code()` while token fetch uses corpus-aware code mapping.

Implementation steps:
- Use the same corpus-aware resolver in every lexical query.
- Add examples for books with differing corpus codes.

Acceptance criteria:
- Chapter/verse availability matches token fetch behavior.

Tests:
- Add corpus-specific code mapping tests.
