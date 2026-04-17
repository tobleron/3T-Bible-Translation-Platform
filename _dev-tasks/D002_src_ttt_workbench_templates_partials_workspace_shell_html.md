# Task D002: Review src/ttt_workbench/templates/partials/workspace_shell.html

## Why This Exists

`src/ttt_workbench/templates/partials/workspace_shell.html` is a `template` file with an estimated risk score of `7.67`.

## Metrics

- LOC: `1993` (preferred `260`, hard ceiling `420`)
- Language: `template`
- Branches: `0`
- Max nesting: `0`
- Mutable assignments: `0`
- Imports: `0`
- Callables/classes: `0`

## Findings

- `medium` `size`: 1993 LOC exceeds preferred 260 LOC for role `template`.
- `high` `size`: 1993 LOC exceeds hard ceiling 420 LOC for role `template`.

## Suggested Handling

Keep the next change focused. If refactoring is warranted, split only cohesive behavior into named helper modules and preserve existing route/import compatibility. For browser workbench changes, rerun:

```bash
./ttt.sh test
```
