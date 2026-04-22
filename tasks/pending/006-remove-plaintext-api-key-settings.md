# Remove Plaintext API Key Settings

Severity: high

Evidence: `web_settings.json` persists `local_api_key` and `cloud_api_key`.

Implementation steps:
- Stop writing API keys into web settings.
- Read secrets from environment variables or an explicitly ignored secret store.
- Keep endpoint provider/base URL/model persisted.

Acceptance criteria:
- Saving settings never writes API key values to `.ttt_workbench/web_settings.json`.

Tests:
- Add settings save/load tests proving submitted keys are not persisted.
