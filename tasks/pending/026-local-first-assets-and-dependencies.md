# Local-First Assets And Dependencies

Severity: medium

Evidence: browser template loads fonts/HTMX/Alpine from CDNs; requirements install a spaCy model from GitHub.

Implementation steps:
- Vendor or pin local frontend assets.
- Add SRI/CSP if external assets remain.
- Move spaCy model download into a documented optional install path if needed.

Acceptance criteria:
- Core browser UI works offline after dependencies are installed.

Tests:
- Add static asset serving tests.
