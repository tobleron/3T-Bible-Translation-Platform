# Fix Tooltip And Inline JavaScript XSS

Severity: high

Evidence: gloss tooltip uses `innerHTML` with dataset values; copy buttons embed verse text inside inline `onclick`.

Implementation steps:
- Build gloss tooltip with DOM nodes and `textContent`.
- Replace inline copy text handlers with data attributes and delegated listeners.
- Escape or JSON-encode all data attributes used by JavaScript.

Acceptance criteria:
- Hostile gloss or verse text renders as text and cannot execute HTML/JS.

Tests:
- Add template/Playwright tests for malicious gloss and verse strings.
