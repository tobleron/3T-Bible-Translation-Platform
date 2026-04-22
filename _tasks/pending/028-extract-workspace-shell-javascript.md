# Extract Workspace Shell JavaScript

Severity: medium

Evidence: `workspace_shell.html` contains large inline JS for unrelated behaviors.

Implementation steps:
- Move gloss tooltips, editor autosave, prompt context, and navigation behavior into static modules.
- Keep templates declarative with data attributes.

Acceptance criteria:
- Inline script size is substantially reduced and behavior remains covered.

Tests:
- Add focused JS/Playwright tests for extracted modules.
