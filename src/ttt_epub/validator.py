import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_all_json_files(directory: Path) -> None:
    """
    Abort execution if *any* JSON file inside *directory*
    (checked recursively) is malformed.
    """
    for path in directory.rglob("*.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.error(
                "JSON structure error in %s — Line %s, Col %s: %s",
                path,
                e.lineno,
                e.colno,
                e.msg,
            )
            raise SystemExit(1)
