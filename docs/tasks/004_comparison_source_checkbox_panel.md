# 004 Comparison Source Checkbox Panel

## Objective

Add a browser-based source selection panel that lets the user enable one or more comparison translations and display them beneath the original-language study material for the current chunk.

## Why

The current source repository already supports flat comparison Bibles that can be loaded by alias. The web app should expose this directly as a clear checkbox-driven UI instead of requiring command-line source inspection.

## Initial Supported Sources

Full OT + NT support currently validated for:

- BSB
- CSB
- ESV
- LEB
- LSB
- LSV
- MLV
- NET
- NIV
- NJB
- NKJV
- NLT
- NRSV

NT-only support currently validated for:

- SBLGNT

## Requirements

1. Show a source-selection control for all currently supported aliases
2. Allow multiple sources to be active at once
3. Render selected source texts beneath the original-language study material for the visible verse range
4. Keep OT and NT behavior clear:
   - OT: Hebrew, literal line, optional LXX comparison, then selected English/source translations
   - NT: Greek, literal line, then selected translations
5. Gracefully handle sources that do not exist for the current testament or verse
6. Persist the user’s selected sources during the current session

## Constraints

- Reuse `SourceRepository` alias loading instead of introducing a second source-loading path
- Do not require source file conversion for the already validated flat JSON files
- Clearly label NT-only sources such as `SBLGNT`

## Acceptance Criteria

- The user can tick `ESV`, `NET`, or any other supported source and immediately see the selected text for the current chunk
- Multiple checked sources render in a stable, readable order
- Sources missing the current passage do not break the page
- The selected sources remain active while navigating nearby chunks in the same session
