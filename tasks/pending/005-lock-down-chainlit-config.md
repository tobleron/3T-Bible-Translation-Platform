# Lock Down Chainlit Config

Severity: high

Evidence: `.chainlit/config.toml` uses `allow_origins = ["*"]`, `unsafe_allow_html = true`, broad upload settings, and full CoT.

Implementation steps:
- Restrict origins to local workbench hosts.
- Disable spontaneous arbitrary uploads by default.
- Avoid unsafe HTML unless the thinking block renderer is replaced with a sanitized allowlist.
- Hide full CoT by default.

Acceptance criteria:
- Config no longer enables broad origins, arbitrary uploads, or full CoT exposure by default.

Tests:
- Add config assertions in existing Chainlit config tests.
