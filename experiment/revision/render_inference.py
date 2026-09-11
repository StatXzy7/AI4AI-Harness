"""Render development-calibration results, without implying formal clearance."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from experiment.revision.replay import ROOT, digest


def main():
    out = ROOT/'artifacts/revision_20260910'
    source = out/'repeat_inference.json'
    data = json.loads(source.read_text(encoding='utf-8'))
    names = {'database_null': 'Database null', 'database_interaction': 'Task interaction',
             'database_and_time': 'Interaction + time', 'cache_null': 'Cache null'}
    rows = data['results']
    labels = [f"{names[r['scenario']]} | {r['n_tasks']} x {r['n_repeats']}" for r in rows]
    fig, axes = plt.subplots(1, 3, figsize=(13, 5.8), sharey=True)
    methods = [('database_task_repeat', 'DB / task / repeat', '#176B5B', -.12),
               ('iid_task_repeat', 'IID task / repeat', '#B55669', .12)]
    for method, title, color, offset in methods:
        stats = [r['methods'][method] for r in rows]
        y = np.arange(len(rows)) + offset
        # Wilson bounds describe Monte Carlo precision for empirical coverage,
        # not confidence intervals for an experimental treatment effect.
        p = np.array([s['coverage'] for s in stats])
        n = data['n_sim']
        z = 1.96
        center = (p+z*z/(2*n))/(1+z*z/n)
        half = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
        # Round-off can put a Wilson endpoint a few ulps outside [0,1].
        error_lengths = np.maximum(0., np.vstack([p-center+half, center+half-p]))*100
        axes[0].errorbar(p*100, y, xerr=error_lengths,
                         fmt='o', color=color, markersize=4, capsize=2, label=title)
        axes[1].plot([s['mean_width']*100 for s in stats], y, 'o', color=color, markersize=4)
        axes[2].plot([s['bias']*100 for s in stats], y, 'o', color=color, markersize=4)
    axes[0].axvline(95, color='gray', linestyle='--', linewidth=1)
    axes[0].set_xlim(0, 102)
    axes[2].axvline(0, color='gray', linestyle='--', linewidth=1)
    axes[0].set_yticks(np.arange(len(rows)), labels)
    axes[0].invert_yaxis()
    axes[0].set_xlabel('Empirical coverage (%)')
    axes[1].set_xlabel('Mean interval width (pp)')
    axes[2].set_xlabel('Bias vs fresh target (pp)')
    for ax in axes:
        ax.grid(axis='x', alpha=.2)
        ax.spines[['top', 'right']].set_visible(False)
    fig.legend(*axes[0].get_legend_handles_labels(), loc='upper center', ncol=2, bbox_to_anchor=(.60,.93))
    fig.suptitle('Candidate repeat-inference calibration: simulation only', y=.99)
    fig.text(.02, .02, f"{data['n_sim']} simulated datasets/setting; {data['n_boot']} bootstrap draws; "
             f"{data['n_reference']} independent reference draws. Coverage bars: 95% Wilson Monte Carlo intervals.\n"
             'Fixed anchors and 9 equal-size databases; finite-repeat fresh-policy target, not stable headroom. No formal-design clearance.', fontsize=9)
    fig.tight_layout(rect=(0,.09,1,.88))
    for suffix in ['png', 'pdf']:
        fig.savefig(out/f'repeat_inference.{suffix}', dpi=180)
    plt.close(fig)
    files = [source, Path(__file__), ROOT/'experiment/revision/replay.py',
             out/'repeat_inference.png', out/'repeat_inference.pdf']
    (out/'repeat_inference_assets.json').write_text(json.dumps(
        {p.relative_to(ROOT).as_posix(): digest(p) for p in files}, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
