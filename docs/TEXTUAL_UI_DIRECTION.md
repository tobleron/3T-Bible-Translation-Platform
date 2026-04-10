# Textual UI Direction

This document defines the UI direction for a future `Textual` version of the TTT workbench.

## Goal

Keep commands, errors, and job feedback separate from the translation reference material.

The main screen should have 3 fixed regions:

- top header
- middle split workspace
- bottom prompt

## Proposed Layout

### Header

Always visible.

Shows:

- app name
- version
- current mode
- model name

### Middle Left Pane

Scrollable.

This is the interaction timeline.

It should contain blocks for:

- command entered
- working/progress state
- errors
- model replies
- review results
- commit results

This pane is about activity and outcomes, not reference material.

### Middle Right Pane

Scrollable.

This is the decision-support pane.

It should stay stable while you work on the current chunk.

It should contain these blocks:

1. Current Chunk
   - book / chapter / range
   - chunk type
   - draft title

2. Source Text
   - NT: Greek source
   - OT: Hebrew source first, LXX beneath or beside it

3. Literal English
   - deterministic lexical gloss view
   - grouped by verse

4. Impact Words
   - only important lexical items
   - no filler words

5. Current Draft
   - the working translation text for the current chunk

6. Terminology Memory
   - approved consistency decisions only

7. Next Decision
   - one short block saying what to do next

This pane should not be polluted by:

- transient command errors
- slash help output
- repair logs
- unrelated notices

## Why Textual Fits Better

`Textual` is a better fit for this layout than the current `prompt_toolkit` fullscreen shell because it is designed around:

- layout containers
- scrollable widgets
- stable panes
- styled blocks
- widget focus
- richer terminal UI composition

Official docs:

- Textual: https://textual.textualize.io/
- prompt_toolkit: https://python-prompt-toolkit.readthedocs.io/en/stable/

Textual documentation explicitly exposes:

- layout
- screens
- command palette
- workers
- widgets such as `Input`, `RichLog`, `ListView`, `LoadingIndicator`, `TextArea`
- scrollbar styling

That matches this app better than manually assembling a pseudo-dashboard on top of `prompt_toolkit`.

## Prototype

A runnable Textual shell exists at:

`02_Human_Editorial_Workspace/textual_workbench.py`

Run it from the repo root with:

```bash
./ttt.sh textual
```

The earlier preview file still exists for comparison, but `textual` is now the main experimental Textual shell.
