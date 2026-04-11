# 007 Model Action Feedback, Prompt Tabs, and Chat Context Sources

## Objective

Improve the browser workbench UX around model-powered actions so the interface clearly shows activity, exposes editable enhancement prompts in a dedicated tab, and lets the user control which source context is sent into chat.

## Why

The current model-driven controls can look stalled while waiting for the local model. The Editorial Assistant prompt editors are not discoverable enough, the support-panel custom tweak flow is too hidden, and chat does not yet let the user choose whether draft text or original-language context should be included in the model prompt.

## Scope

- Add visible in-progress feedback for model-powered actions
- Move Editorial Assistant prompt editing into a proper tab inside that article
- Make support-panel custom prompt controls explicit and visible
- Add chat context source selection controls
- Use the selected chat sources when building the browser chat prompt

## Deliverables

1. Loading feedback for browser model actions
2. Editorial Assistant tabs for `Run` and `Prompts`
3. Explicit visible custom-prompt controls in justification and footnote composers
4. Chat context checkboxes for:
   - draft
   - original languages
5. Browser chat prompt logic that respects those selections

## Constraints

- Keep the model-action feedback compact and consistent with the existing UI
- Do not merge Editorial Assistant state into normal chat history
- Allow chat context selections to be empty if the user intentionally deselects all sources
- Preserve the default of `draft` being selected for chat

## Acceptance Criteria

- Model actions no longer look hung; the initiating control clearly shows active work
- Editorial Assistant exposes prompt editing in a dedicated visible tab
- The user can clearly find and use a custom prompt action in support composers
- Chat can be sent with draft only, original languages only, both, or neither
- The model prompt actually changes based on the selected chat context sources
