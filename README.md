# 3T Bible Translation Platform

3T Bible Translation Platform is a local-first Bible translation workbench for drafting, reviewing, justifying, and publishing Bible translation work with a browser UI, flat Bible reference data, and original-language source resources.

## What Is Included

- Browser workbench built with FastAPI, HTMX, Jinja templates, and Chainlit chat.
- Flat Bible reference JSON files in `data/processed/`.
- Editable translation workspace data in `data/final/_HOLY_BIBLE/`.
- Chapter chunk catalog data in `data/final/chapter_chunk_catalog/`.
- Greek SBLGNT / MorphGNT source data in `src/ttt_workbench/sblgnt/`.
- Hebrew OSHB / WLC XML source data in `data/raw/_Original_Languages/HEBREW/morphhb_xml/`.
- EPUB generation tools in `src/ttt_epub/`.

Generated outputs, local sessions, backups, virtual environments, and private environment files are intentionally excluded from Git.

## Quick Start

```bash
./ttt.sh web
```

Then open:

```text
http://127.0.0.1:8765
```

The launcher creates/updates `.venv` from `requirements-workbench.txt` and starts the browser workbench.

## LLM Endpoint

Configuration is loaded from defaults, `config.yaml`, optional local config files, `.env`, then environment variables.

For llama.cpp-compatible local inference, set:

```bash
export TTT_LLAMA_CPP_BASE_URL="http://127.0.0.1:8080/v1"
export TTT_LLAMA_CPP_API_KEY=""
```

The default in `config.yaml` can be changed for your own local or network endpoint.

## Useful Commands

```bash
./ttt.sh web          # Browser workbench
./ttt.sh web-fake     # Browser workbench with fake LLM responses
./ttt.sh test         # Project test command
./ttt.sh smoke        # Scripted UI smoke checks
./ttt.sh epub         # Build EPUB output
```

Quick direct checks:

```bash
.venv/bin/python -m pytest tests -q
.venv/bin/python -m compileall -q src tests
```

## Repository Layout

```text
src/ttt_workbench/     Browser workbench, controller, templates, UI state
src/ttt_webapp/        Compatibility imports for the browser app
src/ttt_core/          Config, data repositories, LLM clients, shared models
src/ttt_epub/          EPUB assembly and validation
src/ttt_converters/    Data conversion utilities
data/processed/        Flat Bible reference JSON files
data/final/            Current editable Bible/chunk catalog data
data/raw/              Original-language source resources
tests/                 Unit and fake-mode web tests
```

## Notes

- Do not commit `.env`, `.ttt_workbench/`, `.venv/`, `output/`, or `version_backup/`.
- Use environment variables for API keys and endpoint overrides.
- The active browser routes live in `src/ttt_workbench/webapp.py`.
- The browser controller/state logic lives in `src/ttt_workbench/controller.py`.
