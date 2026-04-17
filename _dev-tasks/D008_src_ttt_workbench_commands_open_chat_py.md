# Task D008: Review src/ttt_workbench/commands/open_chat.py

## Why This Exists

`src/ttt_workbench/commands/open_chat.py` is a `general-python` file with an estimated risk score of `15.8`.

## Metrics

- LOC: `310` (preferred `430`, hard ceiling `760`)
- Language: `python`
- Branches: `104`
- Max nesting: `5`
- Mutable assignments: `119`
- Imports: `10`
- Callables/classes: `23`

## Findings

- No hard finding; this file is listed because its risk/size score is high.

## Suggested Handling

Keep the next change focused. If refactoring is warranted, split only cohesive behavior into named helper modules and preserve existing route/import compatibility. For browser workbench changes, rerun:

```bash
./ttt.sh test
```
