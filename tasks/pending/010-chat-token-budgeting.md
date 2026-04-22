# Chat Token Budgeting

Severity: high

Evidence: Chainlit sends the last 20 messages directly with no token/context budget.

Implementation steps:
- Add model context limit metadata.
- Build a priority-based context packer.
- Summarize or trim older chat deterministically.

Acceptance criteria:
- Large chat/context inputs are bounded before provider calls.

Tests:
- Unit tests for context packing and trimming order.
