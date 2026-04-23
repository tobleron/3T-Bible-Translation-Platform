#!/usr/bin/env python3
"""
TTT EPUB generator CLI wrapper.

Run as a module from the project root:
    python -m ttt_epub.generate_epub [--md] [--txt]
"""

from __future__ import annotations

import sys
from pathlib import Path

from ttt_core.config import load_config
from ttt_core.data.repositories import ProjectPaths
from ttt_epub.epub_builder import build_bible_epub


def main(argv: list[str] | None = None) -> None:
    argv = argv or sys.argv
    project_root = Path.cwd()
    cfg = load_config(project_root)
    paths = ProjectPaths(repo_root=project_root)
    output_dir = paths.output_dir / "builds"
    output_dir.mkdir(parents=True, exist_ok=True)
    build_bible_epub(
        root=project_root,
        holy_dir=paths.bible_dir,
        output_dir=output_dir,
        generate_md="--md" in argv,
        generate_txt="--txt" in argv,
    )


if __name__ == "__main__":
    main()
