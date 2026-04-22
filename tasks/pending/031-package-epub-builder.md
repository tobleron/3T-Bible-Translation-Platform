# Package EPUB Builder

Severity: medium

Evidence: EPUB scripts mutate `sys.path`, use local imports, and have a separate config loader.

Implementation steps:
- Convert EPUB modules to package-relative imports.
- Use `ttt_core.config` and `ProjectPaths`.
- Keep CLI wrapper thin.

Acceptance criteria:
- EPUB generation works as both module import and CLI command.

Tests:
- Add package import and temp-data build tests.
