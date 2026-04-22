# TTT Workbench Guide

This guide explains the browser workbench workflow (FastAPI + HTMX + Chainlit).

## Launch

From the project root:

```bash
./ttt.sh web
```

Run the verification suite from the root:

```bash
./ttt.sh smoke
```

Then open `http://127.0.0.1:8765`.

## Session Flow

The normal path is:

1. `Home`
2. open a chapter/chunk from navigator
3. `Study` panel (source texts + comparisons)
4. `Editor` panel (draft / lock / commit states)
5. `Chat` panel (Chainlit iframe bound to chunk session)
6. optional `Justifications` + `Footnotes`
7. `Commit` and optional `Generate EPUB`

If a previous chunk is still open, `Home` also offers `Resume Session`.

## Workspace Panels

### 1. Study

The `Study` panel is deterministic and local.

For OT it shows:

- Hebrew first
- Hebrew literal English
- LXX Greek when available
- LXX literal English
- important words

For NT it shows:

- Greek
- literal English
- important words

### 2. Editor

- Edit draft verse text directly in the editor.
- Autosave runs while editing.
- Lock/unlock controls prevent accidental commit while still drafting.
- Commit state switches editor to review mode.

### 3. Chat

- Chat runs inside the Chainlit iframe in the chat panel.
- Chat sessions are scoped to the active chunk.
- Endpoint/provider/model are controlled from the chat panel.
- Discovery failures are surfaced directly in settings and chat UI.

Useful chat-related commands:

```text
/chat
/focus 4-6
/peek 4 ESV,NET,LSB
/analysis refresh 1-5
```

### 4. Commit + EPUB

- Use commit action in editor to apply staged chunk updates.
- EPUB generation uses committed on-disk JSON only.
- Uncommitted draft text is not included in EPUB output.

## Slash Commands

Slash commands remain available for direct control (advanced path).

Examples:

```text
/open Matthew 1
/open Matthew 1:1-17
/study
/chat
/finalize 1-5
/stage 1-5
/title stage
/justify 2-3
/commit
/epub-gen
/quit
```

Use `/help` or the `/` palette for the full command list.
