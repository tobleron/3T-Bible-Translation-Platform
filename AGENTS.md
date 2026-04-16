# TTT Bible Agent Notes

## Active Application

- The browser workbench is the active UI. Launch it with `./ttt.sh web`; the default URL is `http://127.0.0.1:8765`.
- `ttt_webapp.app` and `ttt_webapp.controller` are compatibility shims that import `ttt_workbench.webapp` and `ttt_workbench.controller`. Do not remove them unless all imports, tests, and launch scripts are migrated.
- The main browser routes live in `src/ttt_workbench/webapp.py`.
- The browser controller/state logic lives in `src/ttt_workbench/controller.py`.
- The compact workspace template is `src/ttt_workbench/templates/partials/workspace_shell.html`; the study/context side panel is `src/ttt_workbench/templates/partials/context_panel.html`.

## LLM Endpoint Setup

- Configuration is loaded by `ttt_core.config.load_config()` from defaults, root `config.yaml`, optional `config/default_config.yaml`, `.env`, then environment overrides.
- The current default llama.cpp endpoint is `http://10.0.0.1:8080/v1`.
- `TTT_LLAMA_CPP_BASE_URL`, `TTT_LLAMA_CPP_API_KEY`, and `TTT_LLAMA_CPP_STREAM_TIMEOUT` override endpoint behavior.
- The project should use the direct WireGuard endpoint for llama.cpp. The deprecated auth proxy must not be reintroduced.

## Remote Model Host

- The desktop model host is reachable as `ssh rubox`.
- WireGuard on the desktop exposes `wg0` as `10.0.0.1/24`.
- The desktop also has LAN address `192.168.1.186`, but the workbench should prefer the WireGuard address.
- llama.cpp runs from `/home/r2/Desktop/open-webui` and serves OpenAI-compatible endpoints.
- Direct llama.cpp is on port `8080`; Open WebUI is on port `8082`.
- The browser workbench has one llama.cpp endpoint setting and should normally use `http://10.0.0.1:8080/v1`.

## Streaming Chat

- Browser chat streaming is implemented by `chat_turn_stream()` and `_sse_chat_stream()` in `src/ttt_workbench/webapp.py`.
- The server streams SSE tokens from `LlamaCppClient.stream_generation()` and emits `event: done` with `data: [DONE]` when complete.
- llama.cpp thinking output arrives as `reasoning_content`; `src/ttt_core/llm/llama_cpp.py` wraps that stream in `<think>...</think>` markers for the browser renderer.
- The browser renderer creates a new assistant entry per prompt and must append thinking/output only to that new entry. Do not use a global `id` for the stream buffer; use the local `assistantEntry.querySelector('[data-chat-stream-buffer]')` pattern.
- Thinking blocks should render as collapsed `<details class="thinking-block">` sections and should not jump to earlier chat messages on later prompts.

## State And Sessions

- Persistent workbench state is under `.ttt_workbench/`.
- Per-chunk browser chat sessions are stored in `.ttt_workbench/chunk_sessions.json` or `.ttt_workbench/browser_fake_mode/chunk_sessions.json` during fake-mode tests.
- `BrowserWorkbench._save_chunk_sessions()` creates the parent directory before writing; preserve that guard because tests remove fake-mode state between cases.

## Testing

- Use `./ttt.sh test` for the project test command.
- For quick direct verification, run `.venv/bin/python -m pytest tests -q`.
- Fake LLM mode is controlled by `TTT_WEBAPP_FAKE_LLM=1`; tests set it automatically in `tests/conftest.py`.
- A lightweight syntax check is `.venv/bin/python -m compileall -q src tests`.

## Editing Guidelines

- Preserve user changes in the worktree. This repo often has active uncommitted edits.
- Keep browser compatibility wrappers until callers are updated.
- Prefer focused fixes in the active `ttt_workbench` modules over touching archived legacy code.
- Do not expose API keys or old removed proxy tokens in logs, docs, tests, or final responses.
