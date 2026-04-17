# Task D011: Review src/ttt_workbench/app.py

## Why This Exists

`src/ttt_workbench/app.py` is a `general-python` file with an estimated risk score of `11.61`.

## Metrics

- LOC: `342` (preferred `430`, hard ceiling `760`)
- Language: `python`
- Branches: `54`
- Max nesting: `5`
- Mutable assignments: `80`
- Imports: `52`
- Callables/classes: `24`

## Findings

- No hard finding; this file is listed because its risk/size score is high.

## Suggested Handling

Keep the next change focused. If refactoring is warranted, split only cohesive behavior into named helper modules and preserve existing route/import compatibility. For browser workbench changes, rerun:

```bash
./ttt.sh test
```
