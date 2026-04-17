# 017 Lazy Render Heavy Panels

## Default Choice

Lazy-load rarely used heavy UI surfaces such as book JSON browsing and large hidden panels.

## Objective

Reduce initial DOM work for every workspace page.

## Acceptance Criteria

- JSON browser content loads only when opened.
- Hidden or collapsed panels avoid unnecessary heavy rendering where practical.
- Study/source sections remain readable and stable.

