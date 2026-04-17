# 001 Aggregate Chapter Chunk Data by Book

## Objective

After the chapter chunk extraction run is complete, safely aggregate the per-chapter chunk JSON files into a per-book data set that can be used by later tools and the web app.

## Why

The chunk generator writes one JSON file per chapter for resilience and resumability. That is good for generation, but downstream consumers will also need book-level access to chunk data without walking hundreds of chapter files manually.

## Scope

- Read completed chapter chunk files from the chapter chunk catalog
- Group them by testament and book
- Produce one aggregated JSON file per book
- Preserve chapter-level chunk metadata inside each book file
- Record missing or failed chapters clearly instead of silently hiding gaps

## Requirements

1. Input source must be the generated chapter chunk catalog
2. Aggregation must be deterministic and repeatable
3. Output must keep chapter ordering intact
4. Output must preserve each chunk’s:
   - start verse
   - end verse
   - type
   - title
   - reason
5. Aggregation must detect and report:
   - missing chapters
   - failed chapters
   - duplicate chapter files
6. Aggregation must not overwrite good outputs silently if input data is incomplete

## Deliverables

1. A script that aggregates chapter chunk JSON into one file per book
2. An output directory for aggregated chunk data
3. A manifest or report identifying missing/failed chapters
4. Safe rerun behavior

## Acceptance Criteria

- Each completed book has a single aggregated JSON file
- Aggregated files are ready for later import into the browser app data layer
- Books with incomplete chapter coverage are reported clearly
- No manual copy-paste is required to use the generated chunk data later
