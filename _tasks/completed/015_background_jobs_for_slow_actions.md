# 015 Add Background Jobs for Slow Actions

## Default Choice

Use a small in-process job registry for this local single-user app before adding Redis/Celery.

## Objective

Return immediately from slow model and EPUB actions, then poll or stream job status.

## Acceptance Criteria

- Long actions can return a job id immediately.
- The UI displays queued/running/succeeded/failed states.
- EPUB generation and model enhancement are candidates for migration.

## Status

Completed for the local in-process job registry path. EPUB generation can start with `POST /epub/jobs/generate`, job state can be read from `GET /jobs/{job_id}` and `GET /jobs`, and active jobs can be cancelled with `POST /jobs/{job_id}/cancel`. Model enhancement remains a candidate for future migration onto the same job API if it becomes too slow for direct JSON responses.
