#!/usr/bin/env python3
"""
Fix curly-apostrophes and audit smart-quote balance in Bible JSON files.

 • Recurses through dirs unless a single file/dir is supplied.
 • Replaces curly single quotes between letters with straight '   (in place).
 • Logs each change:  line N  “can’t”  ->  "can't"
 • After fixing, reports any unmatched opening/closing  “ ”  ‘ ’.
"""

from __future__ import annotations
import argparse, sys, re, json, os
from pathlib import Path

# ——— Unicode quote chars ———
O_DQ, C_DQ = "\u201C", "\u201D"     # “ ”
O_SQ, C_SQ = "\u2018", "\u2019"     # ‘ ’
QUOTE_PAIR = {O_DQ: C_DQ, O_SQ: C_SQ}
CLOSERS    = {C_DQ, C_SQ}
OPENERS    = {O_DQ, O_SQ}

# ——— regex that finds a curly single-quote between *letters* ———
try:                                 # prefer the `regex` module for \p{L}
    import regex as _re
    RX_APO = _re.compile(rf"(\p{{L}})[{O_SQ}{C_SQ}](\p{{L}})")
except ModuleNotFoundError:          # fallback: any unicode letter except digit/_
    RX_APO = re.compile(rf"([^\W\d_])[{O_SQ}{C_SQ}]([^\W\d_])", re.UNICODE)

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def iter_json_files(target: Path) -> list[Path]:
    """Return every *.json* file under *target* (file or dir)."""
    if target.is_file() and target.suffix.lower() == ".json":
        return [target]
    return [p for p in target.rglob("*.json") if p.is_file()]

class Balancer:
    """Stack-based checker for unmatched curly quotes."""
    __slots__ = ("stack", "issues")
    def __init__(self): self.stack, self.issues = [], []
    def feed(self, ch, ln):
        if ch in OPENERS:
            self.stack.append((ch, ln))
        elif ch in CLOSERS:
            if not self.stack or QUOTE_PAIR[self.stack[-1][0]] != ch:
                self.issues.append(f"line {ln}: unmatched closing {repr(ch)}")
            else:
                self.stack.pop()
    def finish(self, last_ln):
        while self.stack:
            opener, ln = self.stack.pop()
            self.issues.append(f"line {last_ln}: missing closing "
                               f"{repr(QUOTE_PAIR[opener])} for opener at line {ln}")

# --------------------------------------------------------------------------- #
# core per-file routine
# --------------------------------------------------------------------------- #
def process_file(fp: Path):
    original_lines = fp.read_text(encoding="utf-8").splitlines(keepends=True)

    changes: list[str] = []
    fixed_lines = []

    # 1) apostrophe fix pass (line by line so we have real line numbers)
    for ln, line in enumerate(original_lines, 1):
        def _repl(m):
            before = m.group(0)
            after  = f"{m.group(1)}'{m.group(2)}"
            changes.append(f"line {ln}: {before!r} -> {after!r}")
            return after
        fixed_line = RX_APO.sub(_repl, line)
        fixed_lines.append(fixed_line)

    # 2) write back if anything changed
    if changes:
        fp.write_text("".join(fixed_lines), encoding="utf-8")
        print(f"\n✏️  {fp}  —  {len(changes)} curly-apostrophe fix(es)")
        for c in changes:
            print("   ", c)
    else:
        print(f"\n✓  {fp}  —  no curly-apostrophes to fix")

    # 3) unmatched-quote audit on the *fixed* content
    balancer = Balancer()
    in_json_string = False
    escape_next = False

    for ln, line in enumerate(fixed_lines, 1):
        for ch in line:
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_json_string = not in_json_string
                continue
            if in_json_string:
                balancer.feed(ch, ln)

    balancer.finish(len(fixed_lines))
    if balancer.issues:
        print("   ⚠️  unmatched quotes:")
        for msg in balancer.issues:
            print("      ", msg)
    else:
        print("   ✅  all curly quotes balanced")

# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None):
    p = argparse.ArgumentParser(
        description="Fix curly-apostrophes and audit curly quotes in JSON Bibles")
    p.add_argument("target", nargs="?", default=".",
                   help="file or directory (default: current dir)")
    args = p.parse_args(argv)

    files = iter_json_files(Path(args.target).expanduser().resolve())
    if not files:
        sys.exit(f"No .json files found under {args.target!r}")

    for f in files:
        process_file(f)

if __name__ == "__main__":
    main()
