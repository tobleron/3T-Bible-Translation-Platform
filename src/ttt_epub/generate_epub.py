#!/usr/bin/env python3
"""
Wrapper script – run this file exactly the way you used to run
*generate_epub_v13.7.py*.  All heavy-lifting now lives in epub_builder.py
so it’s easier to maintain and test.
"""

import sys
from pathlib import Path

# Add project root and src to sys.path to allow importing ttt_core
project_root = Path(__file__).parent.parent.parent.resolve()
src_root = project_root / "src"
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

try:
    from ttt_core.config import load_config
    from ttt_core.data.repositories import ProjectPaths
    from epub_builder import build_bible_epub
except ImportError as e:
    print(f"ImportError: {e}")
    # Fallback to local discovery if ttt_core is not available
    from utils import root_paths
    from epub_builder import build_bible_epub
    ROOT, HOLY_DIR = root_paths(__file__)
    OUTPUT_DIR = ROOT / "output" / "builds"
else:
    cfg = load_config(project_root)
    paths = ProjectPaths(repo_root=project_root)
    ROOT = project_root
    HOLY_DIR = paths.bible_dir
    OUTPUT_DIR = paths.output_dir / "builds"

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    build_bible_epub(
        root=ROOT,
        holy_dir=HOLY_DIR,
        output_dir=OUTPUT_DIR,
        generate_md="--md" in sys.argv,
        generate_txt="--txt" in sys.argv,
    )

if __name__ == "__main__":
    main()
