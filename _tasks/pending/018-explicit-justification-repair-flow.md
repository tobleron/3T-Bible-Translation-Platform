# Explicit Justification Repair Flow

Severity: high

Evidence: unreadable justification files are reinitialized in memory and normalization can drop bad entries.

Implementation steps:
- Treat unreadable critical files as blocking until repair is confirmed.
- Preserve raw files.
- Show repair diff before staging normalized output.

Acceptance criteria:
- Corrupt justification content cannot be silently replaced with an empty document.

Tests:
- Add corrupt justification and explicit repair confirmation tests.
