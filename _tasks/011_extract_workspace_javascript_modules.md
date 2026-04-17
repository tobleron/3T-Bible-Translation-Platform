# 011 Extract Workspace JavaScript Modules

## Default Choice

Extract new interaction code into static files first, then incrementally move legacy inline functions out of `workspace_shell.html`.

## Objective

Reduce the size and fragility of the workspace template and make browser behavior easier to test.

## Acceptance Criteria

- New shared interaction behavior is served from `src/ttt_workbench/static/js/`.
- `base.html` loads the shared module.
- Future work can move chat, autosave, support formatting, JSON browser, and prompt-builder code into separate modules.

