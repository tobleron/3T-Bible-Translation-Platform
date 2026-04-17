# 017 Lazy Render Heavy Panels

## Default Choice

Lazy-load rarely used heavy UI surfaces such as book JSON browsing and large hidden panels.

## Objective

Reduce initial DOM work for every workspace page.

## Acceptance Criteria

- JSON browser content loads only when opened.
- Hidden or collapsed panels avoid unnecessary heavy rendering where practical.
- Study/source sections remain readable and stable.

## Status

Completed. The JSON browser modal is now created by the lazy panel controller only when opened, book/chapter JSON is still fetched on demand, and heavier study/support blocks use rendering containment while preserving readable layout.
