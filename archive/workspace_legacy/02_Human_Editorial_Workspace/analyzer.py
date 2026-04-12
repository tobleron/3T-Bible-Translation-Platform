import re, math
from typing import Dict, List, Set

WORD_RE = re.compile(r"\b[\w'-]+\b")
VOWEL_RE = re.compile(r'[aeiouy]+', re.I)

def tokenize(text: str) -> List[str]:
    return WORD_RE.findall(text.lower())

def syllables(word: str) -> int:
    count = len(VOWEL_RE.findall(word)) or 1
    if word.endswith('e') and not word.endswith('le') and count > 1:
        count -= 1
    return count

def fres(w,s,sy): return 206.835 - 1.015*(w/s) - 84.6*(sy/w)
def fkgl(w,s,sy): return 0.39*(w/s) + 11.8*(sy/w) - 15.59
def gfi(w,s,cw):  return 0.4*((w/s)+100*(cw/w))
def smog(cw,s):   return 1.043*math.sqrt(cw*(30/s))+3.1291 if s else 0
def ari(c,w,s):   return 4.71*(c/w)+0.5*(w/s) - 21.43
def cli(c,w,s):   L=(c/w)*100; S=(s/w)*100; return 0.0588*L - 0.296*S -15.8
def ndc(w,p,s):   return 0.1579*p + 0.0496*(w/s) + (3.6365 if p>5 else 0)
def lix(w,lw,s):  return (w/s)+(lw*100/w)
def rix(lw,s):    return lw/s if s else 0
def herdan(u,w):  return math.log(u)/math.log(w) if w>1 and u else 0

def analyze(text: str, easy: Set[str]) -> Dict[str, float]:
    words = tokenize(text)
    w = len(words)
    u = len(set(words))
    c = sum(len(t) for t in words)
    sy = sum(syllables(t) for t in words)
    s = max(1, sum(text.count(p) for p in '.!?'))
    cw = sum(1 for t in words if syllables(t) >= 3)
    lw = sum(1 for t in words if len(t) > 6)
    diff = sum(1 for t in words if t not in easy)
    diff_pct = diff * 100 / w if w else 0
    return {
        'Word Count': w,
        'Verse Count': s,
        'Unique Words': u,
        'Type‑Token Ratio (%)': round(u*100/w,2) if w else 0,
        'Herdan\'s C': round(herdan(u,w),3),
        'Avg Word Length': round(c/w,2) if w else 0,
        'Flesch Reading Ease': round(fres(w,s,sy),2),
        'Flesch‑Kincaid Grade': round(fkgl(w,s,sy),2),
        'Gunning Fog Index': round(gfi(w,s,cw),2),
        'SMOG Index': round(smog(cw,s),2),
        'Automated Readability Index': round(ari(c,w,s),2),
        'Coleman‑Liau Index': round(cli(c,w,s),2),
        'New Dale–Chall': round(ndc(w,diff_pct,s),2),
        'LIX': round(lix(w,lw,s),2),
        'RIX': round(rix(lw,s),2),
        '% Difficult Words': round(diff_pct,2),
        'Long Words (>6)': lw
    }
