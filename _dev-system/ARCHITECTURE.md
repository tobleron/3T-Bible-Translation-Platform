# _dev-system Architecture

The analyzer is a lightweight feedback loop for this repository:

```text
repo files
  -> scoped discovery
  -> language-aware metrics
  -> role inference
  -> risk scoring
  -> advisory task synthesis
  -> _dev-tasks/
```

## Repository Roles

- `browser-controller`: state transitions and browser editor/session behavior.
- `browser-route`: FastAPI route handlers and SSE streaming.
- `template`: Jinja/HTML partials.
- `style`: CSS for the browser workbench.
- `llm-client`: llama.cpp/OpenAI-compatible client and stream handling.
- `data-repository`: file-backed Bible/chunk/session repositories.
- `epub-builder`: EPUB export pipeline.
- `compat-shim`: modules that preserve old import paths.
- `test`: pytest coverage.
- `tool-script`: project utility scripts.
- `config`: project configuration.

## Risk Signals

Python files are scored with:

- non-comment LOC
- AST branch count
- maximum nesting depth
- mutable assignment count
- import count
- async/function/class count
- path depth
- forbidden patterns

Non-Python files receive lighter checks for size and project-specific forbidden patterns.

## Project-Specific Policy

The analyzer is tuned for a Python web application with a browser workbench:

- Keep `src/ttt_webapp/*` compatibility shims unless all imports and launch paths are migrated.
- Do not reintroduce the deprecated auth proxy; direct llama.cpp endpoint settings belong in config/env.
- Do not expose `.env`, local state, local databases, archives, or generated output in Git.
- Keep active browser behavior in `src/ttt_workbench/webapp.py` and `src/ttt_workbench/controller.py`.
- Treat Bible data and source-language files as publish assets, not lint targets.

## Output Contract

- `_dev-system/reports/latest.json`: full scan report.
- `_dev-tasks/D###_*.md`: advisory tasks sorted by severity.
- `_dev-tasks/README.md`: task system usage.

