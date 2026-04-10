"""Re-export utilities from ttt_core for backward compatibility."""

from ttt_core.utils import (
    book_abbrev,
    book_ref_code,
    ensure_parent,
    extract_json_payload,
    find_close_command,
    make_text_hash,
    normalize_book_key,
    parse_range,
    parse_reference,
    reference_key,
    repair_linewise_json_strings,
    utc_now,
)

__all__ = [
    "book_abbrev",
    "book_ref_code",
    "ensure_parent",
    "extract_json_payload",
    "find_close_command",
    "make_text_hash",
    "normalize_book_key",
    "parse_range",
    "parse_reference",
    "reference_key",
    "repair_linewise_json_strings",
    "utc_now",
]
