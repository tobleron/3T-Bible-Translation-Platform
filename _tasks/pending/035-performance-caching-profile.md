# Performance Caching And Profiling

Severity: medium

Evidence: workspace payload, navigator, project summary, and source loops perform repeated scans/builds.

Implementation steps:
- Profile realistic workspace loads.
- Add targeted caches with file-mtime or commit invalidation.
- Remove repeated calls inside tight loops.

Acceptance criteria:
- Workspace and home route render times improve without stale data.

Tests:
- Add lightweight performance/regression assertions where stable.
