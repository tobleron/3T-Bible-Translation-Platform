# 018 Add Frontend Performance Instrumentation

## Default Choice

Add lightweight development-only timing logs in static JavaScript, controlled by localStorage.

## Objective

Measure click-to-request, request duration, swap target, response size, and stream first-token latency.

## Acceptance Criteria

- Performance logs can be enabled without code changes.
- HTMX request durations are recorded.
- Slow interactions can be identified from browser console diagnostics.

