# Update Browser Docs And Qwen Copy

Severity: medium

Evidence: docs and UI strings still describe older TUI/Qwen-specific workflows.

Implementation steps:
- Make browser workbench docs canonical.
- Mark TUI docs legacy if still retained.
- Replace model-specific copy with active provider/model labels.

Acceptance criteria:
- Docs and UI reflect the current browser + Chainlit workflow.

Tests:
- Add lightweight docs/string checks where valuable.
