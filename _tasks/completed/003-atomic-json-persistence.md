# Atomic JSON Persistence

Severity: high

Evidence: active state, chunk sessions, and web settings are written directly with `Path.write_text()`.

Implementation steps:
- Add a JSON persistence helper using temp files, fsync, atomic replace, and per-file locking.
- Use it for active session, chunk sessions, and web settings.
- Add recovery behavior for invalid primary JSON where a backup exists.

Acceptance criteria:
- Writes are atomic and never leave truncated JSON after simulated failures.

Tests:
- Unit tests for atomic write, invalid JSON recovery, and concurrent writes.
