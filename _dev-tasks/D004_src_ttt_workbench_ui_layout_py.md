# Task D004: Review src/ttt_workbench/ui/layout.py

## Why This Exists

`src/ttt_workbench/ui/layout.py` is a `general-python` file with an estimated risk score of `22.65`.

## Metrics

- LOC: `689` (preferred `430`, hard ceiling `760`)
- Language: `python`
- Branches: `133`
- Max nesting: `9`
- Mutable assignments: `163`
- Imports: `30`
- Callables/classes: `58`

## Findings

- `medium` `size`: 689 LOC exceeds preferred 430 LOC for role `general-python`.

## Suggested Handling

Keep the next change focused. If refactoring is warranted, split only cohesive behavior into named helper modules and preserve existing route/import compatibility. For browser workbench changes, rerun:

```bash
./ttt.sh test
```
