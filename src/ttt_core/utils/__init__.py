"""Utility functions for book codes, parsing, JSON handling, and backups."""

from ttt_core.utils.common import (
    book_abbrev,
    book_ref_code,
    ensure_parent,
    extract_json_payload,
    find_close_command,
    lexical_book_code,
    make_text_hash,
    normalize_book_key,
    parse_range,
    parse_reference,
    reference_key,
    repair_linewise_json_strings,
    utc_now,
)
from ttt_core.utils.backup import (
    restore_backup_set,
    write_backup_set,
)

__all__ = [
    "book_abbrev",
    "book_ref_code",
    "ensure_parent",
    "extract_json_payload",
    "find_close_command",
    "lexical_book_code",
    "make_text_hash",
    "normalize_book_key",
    "parse_range",
    "parse_reference",
    "reference_key",
    "repair_linewise_json_strings",
    "utc_now",
    "restore_backup_set",
    "write_backup_set",
]
