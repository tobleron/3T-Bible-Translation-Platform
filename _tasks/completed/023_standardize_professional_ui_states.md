# 023 Standardize Professional UI States

## Default Choice

Use consistent visual states across the app: idle, pending, saving, saved, failed, retrying, streaming, stopped.

## Objective

Make every user action visibly acknowledged and professionally recoverable.

## Acceptance Criteria

- Buttons and forms share consistent loading/error/success behavior.
- Toasts/status messages use consistent tone classes.
- Long actions show explicit progress state rather than appearing frozen.

## Status

Completed. Workspace toasts now use standardized `info`, `success`, `warning`, and `error` tone classes. Model and EPUB actions share disabled/loading/`aria-busy` behavior, and EPUB generation shows explicit progress plus success/error recovery.
