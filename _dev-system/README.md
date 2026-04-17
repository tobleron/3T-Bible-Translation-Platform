# _dev-system

`_dev-system` is the repository maintenance analyzer for the 3T Bible Translation Platform.

It is adapted from the `elma-cli` development-system idea, but rebuilt for this Python/FastAPI/Jinja/Chainlit stack. The Rust-specific analyzer, stress tests, model configs, and CLI scenarios from `elma-cli` are intentionally not copied.

## What It Does

1. Scans source, tests, scripts, templates, and project configuration.
2. Scores Python files for estimated edit risk using LOC, AST complexity, nesting, mutable state, imports, and path depth.
3. Checks web templates, CSS, shell scripts, YAML, and JSON with lighter file-size and forbidden-pattern rules.
4. Writes advisory markdown tasks into `_dev-tasks/`.
5. Writes a machine-readable report to `_dev-system/reports/latest.json`.

## Run

```bash
./_scripts/run_dev_analyzer.sh
```

The analyzer has no third-party dependencies. It uses the active Python interpreter and standard library only.

## Scope

Included:

- `src/`
- `tests/`
- `ttt.sh`
- `.chainlit/config.toml`
- `config.yaml`
- `requirements-workbench.txt`
- `README.md`
- `PROJECT_GUIDE.md`

Excluded:

- Bible data under `data/`
- runtime state under `.ttt_workbench/`
- virtualenvs and Python caches
- output/build folders
- moved-out or legacy archive folders
- `_dev-system/`, `_dev-tasks/`, and `_scripts/`

## How To Use Tasks

Open `_dev-tasks/`, pick one advisory task, make the smallest coherent change, then run:

```bash
./ttt.sh test
./_scripts/run_dev_analyzer.sh
```

Tasks are guidance, not mandatory failures. The analyzer is conservative because `controller.py`, `webapp.py`, data repositories, and EPUB generation are intentionally coordination-heavy modules.

