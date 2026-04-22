# Schema-Versioned State

Severity: medium

Evidence: persisted state/settings/catalogs are loose dicts/dataclasses and do not round-trip every field.

Implementation steps:
- Add schema versions and typed validation models.
- Implement explicit migrations.
- Fail loudly for invalid critical state.

Acceptance criteria:
- Persisted state validates on load and migrates predictably.

Tests:
- Add migration and invalid state tests.
