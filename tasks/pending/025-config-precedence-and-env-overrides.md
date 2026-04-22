# Config Precedence And Env Overrides

Severity: medium

Evidence: config docs disagree on precedence; stream timeout env handling is split between config and client.

Implementation steps:
- Define one precedence order.
- Move all env override handling into `ttt_core.config`.
- Improve `.env` parsing or use `python-dotenv`.

Acceptance criteria:
- Config docs, tests, and runtime behavior agree.

Tests:
- Add root config, default config, `.env`, env override, and invalid timeout tests.
