# 013 Centralize HTMX Busy and Error States

## Default Choice

Use a single static JavaScript module to manage HTMX request timing, duplicate-click protection, button loading labels, and error toasts.

## Objective

Make every HTMX button acknowledge clicks immediately and recover reliably after success, failure, timeout, or network error.

## Acceptance Criteria

- Buttons with `data-loading-label` are disabled and restored consistently.
- Duplicate submissions are suppressed while a request is in flight.
- Errors produce a visible toast/status message.
- Request durations are available for development diagnostics.

