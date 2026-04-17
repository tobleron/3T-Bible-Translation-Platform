# 016 Formalize Chat Stream Frontend Controller

## Default Choice

Keep the current fetch streaming path, but move state handling into a dedicated static controller.

## Objective

Make stream start, stop, timeout, thinking rendering, markdown rendering, and button cleanup predictable.

## Acceptance Criteria

- Chat stream state is owned by one controller/module.
- Markdown rendering is throttled during streaming.
- Send/stop buttons recover on done, abort, error, and timeout.

