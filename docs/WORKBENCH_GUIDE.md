# TTT Workbench Guide

This guide explains the guided fullscreen workflow for the translation workbench.

## Launch

From the project root:

```bash
./ttt.sh
```

Run the verification suite from the root:

```bash
./ttt.sh smoke
```

## Layout

The fullscreen UI has 4 parts:

- Top bar: `TTT Workbench`, current `MODE`, and current `MODEL`
- Workspace: the current guided stage
- Optional history panel: recent commands, notices, errors, and job results
- Input bar: slash commands, chat messages, and justification notes

The UI is stage-based. The workspace does not behave like a raw terminal transcript anymore.

## Main Controls

- `Enter`: select the highlighted guided action when the input is empty
- `Up` / `Down`: move the guided selection when the input is empty
- `/`: open the command palette
- `Esc`: go back one stage, or close the palette
- `F2`: toggle the history panel

Slash commands still work everywhere, but they are now advanced shortcuts. The guided workflow is the primary interface.

## Session Flow

The normal path is:

1. `Home`
2. `New Session`
3. Choose testament
4. Choose book
5. Choose chapter
6. Choose chunk
7. `Study`
8. `Chat`
9. `Review`
10. `Commit Preview`
11. `Commit` or `Generate EPUB`

If a previous chunk is still open, `Home` also offers `Resume Session`.

## Guided Workflow

### 1. Start a Session

From `Home`, choose `New Session`.

Then select:

- testament
- book
- chapter

The workbench then loads cached or model-generated chunk suggestions for that chapter.

### 2. Choose a Chunk

On `Choose Chunk`, move through the suggested ranges and press `Enter`.

Each chunk shows:

- verse range
- chunk type
- title
- short reason

Use `/chunk-refresh` if you want the model to regenerate suggestions.

### 3. Study the Chunk

The `Study` screen is deterministic and offline.

For OT it shows:

- Hebrew first
- Hebrew literal English
- LXX Greek when available
- LXX literal English
- impact words

For NT it shows:

- Greek
- literal English
- impact words

From `Study`, the recommended next step is `Start Chat`.

### 4. Draft in Chat

Choose `Start Chat`, or use:

```text
/chat
```

While in chat:

- plain text goes to Qwen
- the screen keeps the current draft and recent conversation visible
- pressing `Enter` on an empty input activates the highlighted chat action instead

Useful chat-related commands:

```text
/focus 4
/focus 4-6
/peek 4 ESV,NET,LSB
/analysis refresh 1-17
```

### 5. Review

Run review with:

```text
/finalize 1-17
```

That moves the UI to `Editorial Review`.

From there you can:

- revise in chat
- stage text
- stage title
- add justification
- open commit preview

### 6. Commit Preview

Once text or title is staged, the UI moves to `Commit Preview`.

From there you can:

- validate pending JSON
- commit the staged changes
- generate EPUB
- return to the chunk picker

## Slash Commands

Slash commands are still available for direct control.

Examples:

```text
/open Matthew 1
/open Matthew 1:1-17
/study
/chat
/finalize 1-17
/stage 1-17
/title stage
/justify 2-3
/commit
/epub-gen
/quit
```

Use `/help` or the `/` palette for the full command list.

## History Panel

Press `F2` to open or close the history panel.

It shows the recent:

- commands
- working states
- notices
- errors
- review/commit/output results

This keeps the main workspace clean while still preserving command feedback.

## EPUB

Use either:

- the `Preview EPUB` option from `Home`
- or `/epub-gen`

EPUB generation always uses committed JSON on disk. Staged but uncommitted work is not included.
