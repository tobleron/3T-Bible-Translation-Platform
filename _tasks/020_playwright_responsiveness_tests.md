# 020 Add Playwright Responsiveness Tests

## Default Choice

Add Playwright after interaction code is modular enough to test without brittle selectors.

## Objective

Catch button responsiveness, duplicate submits, stream cleanup, and panel swap regressions.

## Acceptance Criteria

- Tests cover loading state and recovery for key buttons.
- Tests verify stream send/stop controls.
- Tests verify small panel swaps do not replace the full workspace unnecessarily.

