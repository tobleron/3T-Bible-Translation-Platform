# Move Generated Fixtures Out Of Src

Severity: low

Evidence: generated chunk catalog logs/prompts/JSON fixtures live under `src/ttt_workbench/scripts`.

Implementation steps:
- Move generated fixtures to `tests/fixtures` or `data/fixtures`.
- Keep only executable scripts under `src`.
- Scrub obsolete endpoint/model metadata if unnecessary.

Acceptance criteria:
- Source package contains maintained code, not generated fixture trees.

Tests:
- Update affected tests to reference new fixture paths.
