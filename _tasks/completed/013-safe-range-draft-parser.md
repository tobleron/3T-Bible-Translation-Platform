# Safe Range Draft Parser

Severity: high

Evidence: ambiguous multi-verse text is assigned to the first verse and blanks the rest.

Implementation steps:
- Reject ambiguous multi-verse parses instead of blanking verses.
- Preserve existing draft/committed text when parse fails.
- Return a user-visible validation message.

Acceptance criteria:
- Ambiguous multi-verse input cannot erase later verses.

Tests:
- Add numbered, block-separated, single-verse, and ambiguous input tests.
