"""Re-export data repositories from ttt_core for backward compatibility."""

from ttt_core.data import (
    BibleRepository,
    ChapterFile,
    JustificationFile,
    JustificationRepository,
    LexicalRepository,
    ProjectPaths,
    SourceRepository,
    restore_backup_set,
    write_backup_set,
)

__all__ = [
    "BibleRepository",
    "ChapterFile",
    "JustificationFile",
    "JustificationRepository",
    "LexicalRepository",
    "ProjectPaths",
    "SourceRepository",
    "restore_backup_set",
    "write_backup_set",
]
