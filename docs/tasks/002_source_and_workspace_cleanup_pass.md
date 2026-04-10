# 002 Source and Workspace Cleanup Pass

## Objective

Perform a second-pass cleanup of the repository after chunk extraction and related data-generation work are stable, with a focus on making the source-data and workspace layout feel more like a maintainable development environment.

## Why

The repository still mixes raw source files, converter scripts, vendor data, generated outputs, and reference material in ways that make navigation and maintenance harder than they should be.

## Scope

- Reorganize source-ingestion areas without breaking active project paths
- Separate active inputs from archival/reference material
- Reduce mixed-format clutter in source folders
- Preserve all historical material, but place it somewhere intentional

## Focus Areas

1. `00_Data_Converters`
2. legacy workspace leftovers
3. non-runtime reference material
4. old generated or experimental files that are no longer part of the active path

## Requirements

1. Keep active runtime paths stable unless a deliberate migration step also updates all references
2. Prefer moving/archive organization over deletion
3. Distinguish clearly between:
   - active runtime files
   - raw source files
   - conversion scripts
   - vendor/reference dumps
   - generated artifacts
   - archives
4. Leave the chunk extraction output path intact while it is active or becomes a downstream dependency

## Deliverables

1. A cleaner source-data layout
2. Archive locations for old or reference-only material
3. Brief documentation of the new structure

## Acceptance Criteria

- The top-level project and source-data areas are easier to scan
- Active runtime files are easier to distinguish from reference material
- Historical files remain recoverable
- Cleanup does not break the live translation/editorial/EPUB pipeline
