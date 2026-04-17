# 016 Formalize Chat Stream Frontend Controller

## Default Choice

Keep the current fetch streaming path, but move state handling into a dedicated static controller.

## Objective

Make stream start, stop, timeout, thinking rendering, markdown rendering, and button cleanup predictable.

## Acceptance Criteria

- Chat stream state is owned by one controller/module.
- Markdown rendering is throttled during streaming.
- Send/stop buttons recover on done, abort, error, and timeout.

## Status

Completed. Chat stream state, DOM recovery, button restoration, and markdown throttling now live in `static/js/chat_stream_controller.js`; the existing fetch/SSE path delegates to that controller while preserving the current parser behavior.
