from pathlib import Path
import re

LEFT_Q, RIGHT_Q = "“", "”"     # smart quotes


def smart_q(text: str, enable: bool) -> str:
    """
    Replace straight double-quotes with curly quotes when *enable* is True.
    """
    if not enable:
        return text
    out, open_q = [], True
    for ch in text:
        if ch == '"':
            out.append(LEFT_Q if open_q else RIGHT_Q)
            open_q = not open_q
        else:
            out.append(ch)
    return "".join(out)


def html_id(raw: str) -> str:
    """
    Generate a safe anchor/id for headings or links.
    """
    return re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-") or "x"


# ───────────────────────────────────────────────────────────────────
#  NEW -- Glossary helpers
# ───────────────────────────────────────────────────────────────────
_GLOSSARY_RE_CACHE = {}


def _compile_glossary_regex(glossary: dict):
    key = id(glossary)
    if key not in _GLOSSARY_RE_CACHE:
        if not glossary:
            _GLOSSARY_RE_CACHE[key] = None
        else:
            pat = r'\b(' + '|'.join(re.escape(w) for w in glossary) + r')\b'
            _GLOSSARY_RE_CACHE[key] = re.compile(pat, flags=re.IGNORECASE)
    return _GLOSSARY_RE_CACHE[key]


def apply_glossary_links(
    text: str,
    glossary: dict,
    *,
    link_target: str = "glossary.xhtml",
    css_class: str = "glossary-word",
) -> str:
    """
    Wrap every glossary word in an <a> tag pointing to glossary.xhtml#word
    (case-insensitive, preserves original capitalisation).
    """
    regex = _compile_glossary_regex(glossary)
    if not regex:
        return text

    def repl(match):
        word = match.group(0)
        return (
            f'<a href="{link_target}#{word.lower()}" '
            f'class="{css_class}">{word}</a>'
        )

    return regex.sub(repl, text)


# ───────────────────────────────────────────────────────────────────
#  ORIGINAL helper that generate_epub.py still needs
# ───────────────────────────────────────────────────────────────────
def root_paths(script_file: str):
    """
    Returns (project_root, _HOLY_BIBLE folder) regardless of caller location.
    """
    root = Path(script_file).parent.resolve()
    holy = root / "_HOLY_BIBLE"
    return root, holy
