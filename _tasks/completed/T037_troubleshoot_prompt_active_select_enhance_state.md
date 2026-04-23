# T037 Troubleshoot Prompt Active Select Enhance State

## Objective

Find and fix the browser workbench regression where changing the Prompt Engineering `Active prompt` dropdown incorrectly turns the `Enhance` button into `Enhancing...`.

## Observed Failure

In the Prompt Engineering `Prompts` tab, selecting a different active prompt should only switch the prompt being edited. Instead, the `Enhance` button enters its loading state and displays `Enhancing...` even though the user did not click `Enhance`.

This has persisted after an attempted isolation of enhance loading behavior, so the next pass must treat this as an unresolved UI state/regression debugging task rather than assuming the previous code-path analysis was sufficient.

## Reproduction Steps

1. Launch the browser workbench with `./ttt.sh web`.
2. Open `http://127.0.0.1:8765`.
3. Open a workspace chunk that shows the Prompt Engineering panel.
4. Switch to the `Prompts` tab.
5. Use the `Active prompt` dropdown to select a different prompt.
6. Observe whether the `Enhance` button changes to `Enhancing...`.

Expected: the selected prompt changes in-place, the tab remains on `Prompts`, and the `Enhance` button remains labeled `Enhance`.

Actual: the `Enhance` button changes to `Enhancing...` on active prompt selection.

## Suspected Files

- `src/ttt_workbench/templates/partials/workspace_shell.html`
  - Prompt Engineering form markup
  - `Active prompt` select
  - `Enhance` button attributes and inline handlers
- `src/ttt_workbench/static/js/workspace_prompt_engineering.js`
  - `switchActivePrompt`
  - `submitPromptAction`
  - `submitEnhancePrompt`
  - prompt-tab initialization and event binding
- `src/ttt_workbench/static/js/workspace_workspace_actions.js`
  - global button loading helpers and form submit handling
- `src/ttt_workbench/webapp.py`
  - `/editorial` route action handling for `switch_prompt`, `save_prompts`, and `enhance_prompt`
- `tests/test_webapp_fake_mode.py`
  - current coverage proves backend rendering paths but does not prove browser event ordering or button state behavior

## Initial Hypotheses

1. The `change` event on the active prompt select triggers more than `switchActivePrompt`, possibly through shared prompt-panel listeners or HTMX form handling.
2. HTMX preserves or reapplies a disabled/loading button state during the panel swap.
3. A previous transient `action=enhance_prompt` hidden input remains in the form or is recreated unexpectedly.
4. The browser submits the form with the wrong submitter, causing generic loading code to pick up the enhance button.
5. The issue is caused by stale JavaScript loaded in the browser cache, and the app needs asset cache-busting or stronger script versioning.
6. The prompt panel is being reinitialized after an HTMX swap and binding duplicate handlers.

## Investigation Plan

1. Reproduce manually in the browser workbench, with DevTools open, before making another code change.
2. Inspect the live DOM before and after selecting a prompt:
   - hidden `action` inputs
   - `prompt_enhance_target_id`
   - `Enhance` button text, disabled state, classes, and `aria-busy`
   - registered event handlers if available
3. Add temporary console instrumentation locally if needed to trace:
   - `switchActivePrompt`
   - `submitPromptAction`
   - `submitEnhancePrompt`
   - form `submit`
   - HTMX lifecycle events on the editorial form
4. Verify whether stale static assets are involved by hard-refreshing and checking the loaded `workspace_prompt_engineering.js` response contents.
5. Add a browser-level regression test if the test stack can exercise this reliably, preferably asserting that changing `[data-prompt-active-select]` does not mutate the Enhance button label.

## Deliverables

1. Root-cause note in this task file or commit summary identifying the exact event/path that mutates the button.
2. A focused fix that makes active prompt selection and enhance loading state independent.
3. Regression coverage if feasible.
4. Manual verification notes for the Prompt Engineering `Prompts` tab.

## Constraints

- Do not remove Prompt Engineering functionality to hide the symptom.
- Do not make active prompt switching navigate back to the `Run` tab.
- Do not let `Save Prompts`, `Add Prompt`, `Delete`, or active prompt selection trigger `Enhancing...`.
- Preserve the existing dynamic prompt checkbox behavior in the `Run` tab.
- Keep compatibility with HTMX panel swaps.

## Acceptance Criteria

- Changing the `Active prompt` dropdown never changes the `Enhance` button label or busy state.
- Clicking `Enhance` is the only action that changes the button to `Enhancing...`.
- `Save Prompts` only saves prompt edits and never triggers enhancement loading.
- Switching active prompts stays on the `Prompts` tab and updates the visible editor in place.
- Existing focused tests still pass:

```bash
.venv/bin/python -m pytest tests/test_webapp_fake_mode.py -q
```

## Resolution Notes

Status: Implemented and verified.

Root cause: `src/ttt_workbench/static/js/app_interactions.js` handled `htmx:beforeRequest` by treating the submitted `.editorial-form` as the request element, then scanning the entire form for the first descendant with `data-loading-label`. In the Prompt Engineering `Prompts` tab, that first descendant was the `Enhance` button, so active-prompt dropdown submissions incorrectly put `Enhance` into the `Enhancing...` busy state.

Fix: `requestControl` now prefers the actual triggering control from the HTMX triggering event, then direct request elements, and returns no busy control for generic form submissions. This prevents forms from borrowing unrelated child loading labels.

Additional Prompt tab fixes found during the pass:

- Non-active prompt texts are now present as hidden prompt values so the Run-tab combined prompt builder can still include a checked prompt even when that prompt is not the active visible editor.
- Persisted Prompt Engineering modes, context checkboxes, and `No Labels` are rendered checked after HTMX swaps instead of being visually reset and then saved back as empty.
- Active prompt dropdown changes no longer participate in the generic prompt-preview/context listener, avoiding a redundant context save during prompt switching.

Verification:

```bash
.venv/bin/python -m pytest tests/test_webapp_fake_mode.py -q
.venv/bin/python -m pytest tests/test_playwright_responsiveness.py -q
```

Results:

- `tests/test_webapp_fake_mode.py`: 22 passed
- `tests/test_playwright_responsiveness.py`: 11 passed
