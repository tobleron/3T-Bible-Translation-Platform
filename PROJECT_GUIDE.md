# 3T Bible Translation Platform: Workflow Guide

## 1. Project Overview

The 3T Bible Translation Platform is a browser-based translation workbench for drafting, reviewing, justifying, and publishing Bible translation work with local or networked LLM endpoints.

The active application is the browser workbench launched by:

```bash
./ttt.sh web
```

## 2. LLM Setup

The platform uses a llama.cpp-compatible OpenAI API endpoint by default and can also use OpenAI when configured.

Configuration is loaded from built-in defaults, root `config.yaml`, optional local config, `.env`, and environment overrides.

Common overrides:

```bash
export TTT_LLAMA_CPP_BASE_URL="http://127.0.0.1:8080/v1"
export TTT_LLAMA_CPP_API_KEY=""
export TTT_LLAMA_CPP_STREAM_TIMEOUT="1800"
```

Use environment variables for API keys. Do not commit credentials.

## 3. Active Modules

### Browser Workbench

- `src/ttt_workbench/webapp.py`: FastAPI routes and HTMX endpoints.
- `src/ttt_workbench/controller.py`: browser controller and persistent workbench state.
- `src/ttt_workbench/chainlit_app.py`: mounted Chainlit chat UI.
- `src/ttt_workbench/templates/`: Jinja templates.
- `src/ttt_workbench/static/`: browser CSS.
- `src/ttt_webapp/`: compatibility imports for existing launcher paths.

### Core

- `src/ttt_core/config.py`: configuration loader.
- `src/ttt_core/data/repositories.py`: Bible, source, justification, lexical, and backup repositories.
- `src/ttt_core/llm/`: llama.cpp and OpenAI-compatible clients.
- `src/ttt_core/models/`: shared dataclasses and state objects.

### EPUB

- `src/ttt_epub/generate_epub.py`: EPUB build entry point.
- `src/ttt_epub/epub_builder.py`: EPUB assembly.
- `src/ttt_epub/validator.py`: output validation helpers.

### Data

- `data/processed/`: flat Bible reference JSON files.
- `data/final/_HOLY_BIBLE/`: editable platform Bible data.
- `data/final/chapter_chunk_catalog/`: chapter chunk metadata used by the browser.
- `data/raw/_Original_Languages/HEBREW/morphhb_xml/`: Hebrew source-language data.
- `src/ttt_workbench/sblgnt/`: Greek SBLGNT / MorphGNT data used by the workbench.

## 4. Main Workflow

1. Start the browser workbench with `./ttt.sh web`.
2. Open a chapter/chunk in the browser.
3. Review source translations and original-language context.
4. Use chat and editorial tools to draft or revise text.
5. Commit approved changes to `data/final/_HOLY_BIBLE/`.
6. Build an EPUB with `./ttt.sh epub`.

## 5. Repository Hygiene

The GitHub repository should include only the runnable platform, tests, documentation, flat Bible data, editable workspace Bible data, and original-language source data.

Excluded from Git:

- `.env`
- `.venv/`
- `.ttt_workbench/`
- `output/`
- `archive/`
- `version_backup/`
- raw cloned `data/raw/bible_databases/`
- cache directories and compiled Python files

## 6. Checks

```bash
./ttt.sh test
.venv/bin/python -m pytest tests -q
.venv/bin/python -m compileall -q src tests
```

**Document Version:** 2.0  
**Updated:** April 18, 2026
