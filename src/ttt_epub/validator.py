import json
from pathlib import Path

def validate_all_json_files(directory: Path) -> None:
    """
    Abort execution if *any* JSON file inside *directory*
    (checked recursively) is malformed.
    """
    for path in directory.rglob("*.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(
                f"❌ JSON structure error in {path} — "
                f"Line {e.lineno}, Col {e.colno}: {e.msg}"
            )
            raise SystemExit(1)
