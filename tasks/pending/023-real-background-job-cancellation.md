# Real Background Job Cancellation

Severity: medium

Evidence: cancellation sets an event but blocking targets do not receive it; EPUB job uses `subprocess.run()`.

Implementation steps:
- Pass cancel events into targets.
- Use cancellable subprocess handling.
- Add cancellation-aware provider calls where possible.

Acceptance criteria:
- Cancelling a running EPUB job terminates the subprocess.

Tests:
- Add cancellation tests that prove the target stops.
