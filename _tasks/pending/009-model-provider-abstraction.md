# Model Provider Abstraction

Severity: high

Evidence: cloud/local settings mutate the same `LlamaCppClient`; `complete_json()` contains Qwen-specific prompt text.

Implementation steps:
- Define a provider interface for model listing, completion, JSON completion, and streaming.
- Implement llama.cpp native, OpenAI-compatible local, and OpenAI providers separately.
- Move model-specific prompt hints into provider/model profiles.

Acceptance criteria:
- Browser provider selection instantiates or resolves the correct provider implementation.

Tests:
- Add provider selection and payload-shape tests.
