# Task 008: Streaming Chat Termination & Thinking Placement

## Status: Updated April 16, 2026

The active browser workbench now talks directly to llama.cpp over WireGuard:

- Endpoint: `http://10.0.0.1:8080/v1`
- Remote host: `rubox`
- llama.cpp systemd service: `llama-default-model.service`
- Open WebUI systemd service: `openwebui.service`

The old authenticated proxy path has been removed from the remote server and should not be used in new diagnostics or code.

## Current Implementation

- Server streaming lives in `src/ttt_workbench/webapp.py` as `chat_turn_stream()` and `_sse_chat_stream()`.
- The server emits keepalive comments while waiting for the model and finishes with `event: done` / `data: [DONE]`.
- `src/ttt_core/llm/llama_cpp.py` reads OpenAI-compatible llama.cpp deltas.
- `reasoning_content` is wrapped in `<think>...</think>` so the browser can render a collapsible thinking block.
- The browser renderer in `src/ttt_workbench/templates/partials/workspace_shell.html` creates one assistant entry per submitted prompt and appends stream output to that entry’s local `[data-chat-stream-buffer]`.

## Bug Fixed

The previous implementation used a global `id="chat-stream-buffer"`. On a second prompt, `document.getElementById()` could resolve to an older assistant response, causing the new thinking block to appear under the first response instead of the current prompt.

The current implementation uses:

```js
var mdBuffer = assistantEntry.querySelector('[data-chat-stream-buffer]');
```

This keeps thinking and final output scoped to the assistant entry created for the active stream.

## Remote Checks

Useful checks:

```bash
ssh rubox 'systemctl is-active llama-default-model.service openwebui.service'
ssh rubox 'ss -ltnp | grep -E ":(8080|8082)\b"'
curl http://10.0.0.1:8080/v1/models
```

Expected open ports on the model host:

- `8080`: llama.cpp OpenAI-compatible endpoint
- `8082`: Open WebUI

No service should listen on `8081`.
