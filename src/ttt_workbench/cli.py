import argparse, random, string, json, re
from datetime import datetime
from pathlib import Path

from analyzer import analyze
from dale_chall import load_easy_wordlist
from dashboard_termgraph import write_dashboard  # uses termgraph

def run(argv=None):
    parser = argparse.ArgumentParser(description="Bible Readability Analyzer")
    parser.add_argument('ranges', nargs='+', help="BOOK:CH or BOOK:CH1-CH2")
    parser.add_argument('--json', action='store_true', help="Produce JSON outputs and summary")
    parser.add_argument('--wordlist', type=str, help="Custom Dale-Chall list")
    args = parser.parse_args(argv)

    ROOT = Path(__file__).parent
    IN_DIR = ROOT / 'FLAT_BIBLES'
    OUT_DIR = ROOT / 'OUTPUT'
    OUT_DIR.mkdir(exist_ok=True)

    easy = load_easy_wordlist(args.wordlist)
    sid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    ts = datetime.now().strftime('%Y%m%d_%H%M')

    stats_list = []
    file_names = []
    produced_json = []
    rng_re = re.compile(r'([^:]+):(\d+)(?:-(\d+))?')

    for rng in args.ranges:
        m = rng_re.match(rng)
        if not m:
            print('Invalid range:', rng)
            continue
        book, start, end = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
        ch_range = f"{start:03d}-{end:03d}" if start != end else f"{start:03d}"

        for bible in sorted(IN_DIR.glob('*.json')):
            try:
                # Read file without BOM and normalize hyphens
                verses = json.loads(bible.read_text(encoding='utf-8').replace('\ufeff', '').replace('\r', ''))
            except Exception as e:
                print('Skip', bible.name, e)
                continue

            filtered = [v for v in verses if v.get('book') == book and start <= v.get('chapter', -1) <= end and 'text' in v]
            text = ' '.join(v.get('text', '') for v in filtered)
            if not text:
                continue

            res = analyze(text, easy)
            res['Verse Count'] = len(filtered)
            # Normalize all non-ASCII hyphens to standard hyphens
            res = {k.replace('‑', '-').replace('–', '-').replace('—', '-'): v for k, v in res.items()}
            base = f"{bible.stem}_{book}_{ch_range}_{ts}_id_{sid}.json"
            if args.json:
                out_path = OUT_DIR / base
                out_path.write_text(json.dumps(res, indent=2, ensure_ascii=False).replace('\r', ''), encoding='utf-8')
                produced_json.append(out_path)
            stats_list.append(res)
            file_names.append(base)
            print('✓', base)

    if args.json and produced_json:
        summary_path = OUT_DIR / f"Bibles_Analysis_Summary_id_{sid}.json"

        last_range = args.ranges[-1]
        m = re.match(r'([^:]+):(\d+)(?:-(\d+))?', last_range)
        book = m.group(1)
        start = int(m.group(2))
        end = int(m.group(3) or m.group(2))
        ch_range = f"{start:03d}-{end:03d}" if start != end else f"{start:03d}"

        bible_summaries = []
        for fname, stat in zip(file_names, stats_list):
            # Normalize hyphens in summary file as well
            normalized_stat = {k.replace('‑', '-').replace('–', '-').replace('—', '-'): v for k, v in stat.items()}
            bible_summaries.append({
                "version": fname.split('_')[0],
                "file": fname,
                **normalized_stat
            })

        output = {
            "summary_id": sid,
            "range": f"{book} {ch_range}",
            "analyzed_on": ts,
            "bibles": bible_summaries
        }

        # Clean up line endings and remove BOM for summary file
        summary_path.write_text(json.dumps(output, indent=2, ensure_ascii=False).replace('\r', ''), encoding='utf-8')
        print('★ Summary', summary_path.name)

        dash_path = OUT_DIR / f"Bibles_Analysis_Summary_id_{sid}_charts"
        dash_path.mkdir(parents=True, exist_ok=True)
        write_dashboard(dash_path, sid, file_names, stats_list, live=True)
        print('★ Dashboard charts saved to', dash_path.name)

        for p in produced_json:
            p.unlink(missing_ok=True)
        print('🧹 Cleaned individual JSON files')
