# 014 Use Native HTMX Sync and Disabled Controls

## Default Choice

Add native HTMX attributes where useful: `hx-sync`, `hx-disabled-elt`, and indicators for forms that can be double-clicked.

## Objective

Reduce custom JavaScript and prevent overlapping requests from the same form/control.

## Acceptance Criteria

- High-risk submit forms use request synchronization.
- Double-clicking a submit control does not send duplicate writes.
- Native HTMX behavior and custom busy-state behavior do not conflict.

