# Task D012: Review src/ttt_workbench/ui/screens/study.py

## Why This Exists

`src/ttt_workbench/ui/screens/study.py` is a `general-python` file with an estimated risk score of `11.39`.

## Metrics

- LOC: `191` (preferred `430`, hard ceiling `760`)
- Language: `python`
- Branches: `79`
- Max nesting: `4`
- Mutable assignments: `60`
- Imports: `4`
- Callables/classes: `12`

## Findings

- No hard finding; this file is listed because its risk/size score is high.

## Suggested Handling

Keep the next change focused. If refactoring is warranted, split only cohesive behavior into named helper modules and preserve existing route/import compatibility. For browser workbench changes, rerun:

```bash
./ttt.sh test
```
