# Task D006: Review src/ttt_workbench/scripts/generate_chapter_chunks.py

## Why This Exists

`src/ttt_workbench/scripts/generate_chapter_chunks.py` is a `tool-script` file with an estimated risk score of `14.73`.

## Metrics

- LOC: `493` (preferred `420`, hard ceiling `720`)
- Language: `python`
- Branches: `84`
- Max nesting: `6`
- Mutable assignments: `108`
- Imports: `20`
- Callables/classes: `26`

## Findings

- `medium` `size`: 493 LOC exceeds preferred 420 LOC for role `tool-script`.

## Suggested Handling

Keep the next change focused. If refactoring is warranted, split only cohesive behavior into named helper modules and preserve existing route/import compatibility. For browser workbench changes, rerun:

```bash
./ttt.sh test
```
