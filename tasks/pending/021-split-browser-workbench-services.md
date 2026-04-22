# Split Browser Workbench Services

Severity: high

Evidence: `BrowserWorkbench` is a large controller that handles storage, settings, chat, editor, study context, commit prep, and rendering payloads.

Implementation steps:
- Extract services for workspace state, editor drafts, chat sessions, study context, settings, and commits.
- Keep the current controller as a temporary facade.

Acceptance criteria:
- New behavior can be implemented in services without adding more controller sprawl.

Tests:
- Add service-level tests as behavior moves out of the controller.
