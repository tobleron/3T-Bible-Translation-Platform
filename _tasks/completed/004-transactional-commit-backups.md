# Transactional Commit Backups

Severity: critical

Evidence: `write_backup_set()` writes targets before the manifest is complete; duplicate backup helpers exist; restore trusts manifest paths.

Implementation steps:
- Consolidate backup helpers into one module.
- Validate all paths under allowed project roots.
- Stage manifest before applying replacements and mark completion afterward.
- Roll back already-written files on failure.

Acceptance criteria:
- Partial commit failures restore prior content.
- Tampered manifests outside allowed roots are rejected.

Tests:
- Add partial failure, rollback, and path traversal tests.
