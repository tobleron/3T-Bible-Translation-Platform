# 015 Add Background Jobs for Slow Actions

## Default Choice

Use a small in-process job registry for this local single-user app before adding Redis/Celery.

## Objective

Return immediately from slow model and EPUB actions, then poll or stream job status.

## Acceptance Criteria

- Long actions can return a job id immediately.
- The UI displays queued/running/succeeded/failed states.
- EPUB generation and model enhancement are candidates for migration.

