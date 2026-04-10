# 005 Chunk Boundary and Label Quality Audit

## Objective

After the chapter chunk extraction run is complete, perform a systematic audit of the generated chunk data to verify that verse boundaries, chunk types, titles, and reasons are accurate enough for downstream use.

## Why

The current generator is producing structurally valid JSON, but a full-bible pass still needs quality control. Some outputs may have correct verse spans but slightly inaccurate type labels, titles, or reasons. This audit should identify those cases before the data is treated as settled.

## Scope

- Review generated chapter chunk JSON outputs after batch generation completes
- Detect likely chunk-boundary mistakes
- Detect weak or inaccurate type/title/reason labeling
- Produce a report of suspicious chapters for manual review
- Preserve good outputs and avoid unnecessary rewrites

## Checks

1. Verse coverage is contiguous and complete
2. Chunk boundaries align with the visible chapter structure
3. One-verse tail chunks are flagged where they look suspicious
4. Chunk `type` values match the actual content
5. Chunk `title` values accurately describe the covered verses
6. Chunk `reason` values do not claim events outside the chunk range
7. Outlier chapters with too many or too few chunks are flagged

## Deliverables

1. An audit script or repeatable review workflow
2. A report of suspicious chapters and why they were flagged
3. A list of chapters safe to accept as-is
4. A list of chapters needing manual correction

## Acceptance Criteria

- The generated chunk dataset has a documented quality-review pass
- Problematic chapters are identified before aggregation or app integration depends on them blindly
- Review work is focused on flagged chapters instead of manual inspection of the entire Bible
