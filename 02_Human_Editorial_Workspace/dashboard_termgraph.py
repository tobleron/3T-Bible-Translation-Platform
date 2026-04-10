import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

def normalize_keys(d):
    """Replace non-breaking and fancy dashes with ASCII hyphens in dictionary keys."""
    return {
        k.replace('‑', '-')  # non-breaking hyphen
         .replace('–', '-')  # en dash
         .replace('—', '-')  # em dash
         .strip(): v
        for k, v in d.items()
    }

def plot_grouped_bar_chart(title, metrics, bibles, data, out_path):
    x = np.arange(len(bibles))
    width = 0.8 / len(metrics)

    fig, ax = plt.subplots(figsize=(10, 6))
    for i, metric in enumerate(metrics):
        values = [d.get(metric, 0) for d in data]
        bars = ax.bar(x + i * width, values, width, label=metric)
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height:.1f}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=8)

    ax.set_ylabel('Value', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.set_xticks(x + width * (len(metrics) - 1) / 2)
    ax.set_xticklabels(bibles, rotation=45, ha='right', fontsize=10)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.20), ncol=len(metrics), fontsize=10)
    ax.grid(axis='y', linestyle='--', linewidth=0.5, alpha=0.7)
    ax.set_ylim(bottom=0)

    fig.tight_layout()
    plt.subplots_adjust(top=0.85)
    plt.savefig(out_path, bbox_inches='tight', dpi=150)
    plt.close()

def save_all_metric_charts(stats_list, file_names, chart_dir):
    short_names = [Path(fn).stem.split('_')[0] for fn in file_names]
    normalized_stats = [normalize_keys(s) for s in stats_list]

    groups = [
        ("Text Volume", ["Word Count", "Verse Count", "Unique Words"]),
        ("Vocabulary Diversity", ["Type-Token Ratio (%)", "Herdan's C"]),
        ("Word Complexity", ["Avg Word Length", "Long Words (>6)", "% Difficult Words"]),
        ("Readability Scores", ["Flesch Reading Ease", "Flesch-Kincaid Grade"]),
        ("Advanced Readability", ["Gunning Fog Index", "SMOG Index", "Automated Readability Index", "Coleman-Liau Index", "New Dale–Chall"]),
        ("Misc Complexity Indices", ["LIX", "RIX"]),
    ]

    for title, metrics in groups:
        out_path = chart_dir / f"{title.replace(' ', '_')}.png"
        plot_grouped_bar_chart(title, metrics, short_names, normalized_stats, out_path)

# 👇👇 This is what __main__.py or cli.py should import
def write_dashboard(dash_path, sid, file_names, stats_list, live=True):
    save_all_metric_charts(stats_list, file_names, dash_path)
