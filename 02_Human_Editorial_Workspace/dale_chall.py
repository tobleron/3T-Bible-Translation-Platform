from pathlib import Path
from typing import Set

def load_easy_wordlist(custom_path: str = None) -> Set[str]:
    if custom_path and Path(custom_path).exists():
        return {ln.strip().lower() for ln in Path(custom_path).read_text(encoding='utf-8').splitlines() if ln.strip()}
    default_path = Path(__file__).parent / 'data' / 'dale_chall_1995.txt'
    return {ln.strip().lower() for ln in default_path.read_text(encoding='utf-8').splitlines() if ln.strip()}
