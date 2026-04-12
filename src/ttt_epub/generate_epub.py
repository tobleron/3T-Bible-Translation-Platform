#!/usr/bin/env python3
"""
Wrapper script – run this file exactly the way you used to run
*generate_epub_v13.7.py*.  All heavy-lifting now lives in epub_builder.py
so it’s easier to maintain and test.
"""

import sys
from utils import root_paths
from epub_builder import build_bible_epub

def main():
    ROOT, HOLY_DIR = root_paths(__file__)
    build_bible_epub(
        root=ROOT,
        holy_dir=HOLY_DIR,
        generate_md="--md" in sys.argv,
        generate_txt="--txt" in sys.argv,
    )

if __name__ == "__main__":
    main()
