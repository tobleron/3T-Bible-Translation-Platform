# Task D009: Review src/ttt_workbench/scripts/prepare_lexical_data.py

## Why This Exists

`src/ttt_workbench/scripts/prepare_lexical_data.py` is a `tool-script` file with an estimated risk score of `12.76`.

## Metrics

- LOC: `228` (preferred `420`, hard ceiling `720`)
- Language: `python`
- Branches: `70`
- Max nesting: `5`
- Mutable assignments: `104`
- Imports: `16`
- Callables/classes: `21`

## Findings

- No hard finding; this file is listed because its risk/size score is high.

## Suggested Handling

Keep the next change focused. If refactoring is warranted, split only cohesive behavior into named helper modules and preserve existing route/import compatibility. For browser workbench changes, rerun:

```bash
./ttt.sh test
```
