# Single Job Runner

Severity: medium

Evidence: FastAPI has `_JOB_RUNNER`; `WorkbenchApp` also has `self.job_runner`; workspace payload and `/jobs` read different runners.

Implementation steps:
- Inject one runner into app/controller/routes.
- Remove duplicate runner state.

Acceptance criteria:
- Workspace job payload and `/jobs` report the same jobs.

Tests:
- Add job visibility tests covering both payloads.
