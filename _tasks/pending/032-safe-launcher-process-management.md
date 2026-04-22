# Safe Launcher Process Management

Severity: medium

Evidence: `ttt.sh` kills any process on a port and uses `pkill -f` for prep/epub.

Implementation steps:
- Use PID files for app-owned processes.
- Avoid killing unknown processes by default.
- Prefer graceful termination.

Acceptance criteria:
- Launcher does not kill unrelated processes.

Tests:
- Add shellcheck-style or scripted dry-run tests where practical.
