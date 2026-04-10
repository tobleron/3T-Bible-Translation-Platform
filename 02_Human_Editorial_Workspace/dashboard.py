from typing import List, Dict
from pathlib import Path
import asciichartpy  # Added for line chart support

def ascii_bar(label: str, value: float, scale: float, char: str):
    return f"{label:<12} {char * int(value * scale)} ({value})"

def sparkline(vals: List[int]) -> str:
    ticks = '▁▂▃▄▅▆▇'
    maxv = max(vals) if vals else 1
    return ''.join(ticks[min(int(v / maxv * 6), 6)] for v in vals)

ALL_METRICS = [
    'Word Count', 'Verse Count', 'Unique Words', 'Type‑Token Ratio (%)',
    'Herdan\'s C', 'Avg Word Length', 'Flesch Reading Ease', 'Flesch‑Kincaid Grade',
    'Gunning Fog Index', 'SMOG Index', 'Automated Readability Index',
    'Coleman‑Liau Index', 'New Dale–Chall', 'LIX', 'RIX',
    '% Difficult Words', 'Long Words (>6)'
]

def write_line_chart(d, title: str, values: List[float]):
    d.write(f"\n[{title} Trend]\n")
    chart = asciichartpy.plot(values, {'height': 8})
    d.write(chart + '\n')

def write_dashboard(path: Path, sid: str, file_names: List[str], stats_list: List[Dict]):
    with path.open('w', encoding='utf-8') as d:
        d.write(f"Dashboard (session {sid})\n{'='*60}\n\n")

        # Word/Verse counts with sparkline
        d.write('[Word & Verse Counts]\n')
        words = [s['Word Count'] for s in stats_list]
        verses = [s['Verse Count'] for s in stats_list]
        max_val = max(words + verses) or 1
        scale = 40 / max_val
        for lbl, w, v in zip(file_names, words, verses):
            short = Path(lbl).stem[:10]
            d.write(ascii_bar(short + ' W', w, scale, '#') + '\n')
            d.write(ascii_bar(short + ' V', v, scale, '*') + '\n')
        d.write('\n[Word Count Timeline]\n' + sparkline(words) + '\n\n')

        # All 17 metrics
        d.write('[Metric Comparisons]\n')
        for metric in ALL_METRICS:
            values = [s.get(metric, 0) for s in stats_list]
            maxv = max(values) or 1
            bar_scale = 40 / maxv
            d.write(f"\n{metric}:\n")
            for fname, val in zip(file_names, values):
                short = Path(fname).stem[:10]
                d.write(ascii_bar(short, val, bar_scale, '|') + '\n')

        # Line charts for select metrics
        write_line_chart(d, "Flesch‑Kincaid Grade", [s['Flesch‑Kincaid Grade'] for s in stats_list])
        write_line_chart(d, "New Dale–Chall", [s['New Dale–Chall'] for s in stats_list])
        write_line_chart(d, "% Difficult Words", [s['% Difficult Words'] for s in stats_list])
        write_line_chart(d, "Word Count", [s['Word Count'] for s in stats_list])