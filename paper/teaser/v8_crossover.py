"""V6 plus the paper's task-wise crossover criterion for stable complementarity.

The two miniature probability sketches are explicitly conceptual. Their
ordinates are qualitative examples, never measured probabilities from the
experiment. The measured coverage and repeatability panels are drawn with the
unchanged v6 routines; the original study illustration is also unchanged.
"""
from __future__ import annotations

import build_v6 as v6


def _conceptual_sketch(ax, x, title, baseline, member, positive):
    """Show two equally weighted task types without numerical probability ticks."""
    headroom = sum(max(a, b) for a, b in zip(baseline, member))/2 - max(
        sum(baseline)/2, sum(member)/2)
    assert headroom > 0 if positive else abs(headroom) < 1e-12
    v6.text(ax, x + 36, 15, title, 7.5, weight='bold', ha='center')
    x0, x1, y0, y1 = x + 7, x + 68, 26, 43
    v6.line(ax, x0, y0, x0, y1, v6.MUTED, .4)
    v6.line(ax, x0, y1, x1, y1, v6.MUTED, .4)
    v6.text(ax, x + 1, 30, 'p', 7.5, v6.MUTED, 'italic', ha='center')
    xs = [x0 + 7, x1 - 6]
    py = lambda p: y1 - 2 - p * 13
    by = [py(p) for p in baseline]
    my = [py(p) for p in member]
    # Shading encodes the alternating better member in the crossover sketch.
    # This is an illustration of the population criterion, not estimated data.
    if positive:
        xm = (xs[0] + xs[1]) / 2
        ym = (by[0] + by[1]) / 2
        ax.fill([xs[0], xm, xs[0]], [by[0], ym, my[0]],
                color='#E4EBF2', zorder=0)
        ax.fill([xm, xs[1], xs[1]], [ym, by[1], my[1]],
                color='#DDEFEA', zorder=0)
    ax.plot(xs, by, color=v6.BLUE, lw=.95, marker='s', markersize=2.4,
            markerfacecolor='white', markeredgewidth=.6, zorder=4)
    ax.plot(xs, my, color=v6.TEAL, lw=.95, ls=(0, (2, 1.2)), marker='o',
            markersize=2.6, markerfacecolor=v6.TEAL,
            markeredgecolor='white', markeredgewidth=.3, zorder=5)
    v6.text(ax, x1, 43, 'Tasks', 7.5, v6.MUTED, ha='right')
    v6.text(ax, x + 36, 51, 'Stable headroom > 0' if positive else 'Stable headroom = 0',
            7.5, v6.TEAL if positive else v6.INK,
            weight='bold', ha='center')


def crossover(ax):
    # All labels fit the original method strip, preserving the v6 composition.
    v6.text(ax, 221, 3, 'Success p · schematic', 7.5, v6.MUTED, 'italic')
    v6.line(ax, 290, 7, 299, 7, v6.BLUE, .95)
    ax.plot(294.5, 7, marker='s', markersize=2.3, color=v6.BLUE,
            markerfacecolor='white', markeredgewidth=.6)
    v6.text(ax, 302, 3, 'Baseline', 7.5, v6.BLUE)
    v6.line(ax, 338, 7, 347, 7, v6.TEAL, .95, ls=(0, (2, 1.2)))
    ax.plot(342.5, 7, marker='o', markersize=2.4, color=v6.TEAL,
            markeredgecolor='white', markeredgewidth=.3)
    v6.text(ax, 350, 3, 'Member', 7.5, v6.TEAL)
    _conceptual_sketch(ax, 221, 'Dominance', [.85, .6], [.55, .3], False)
    _conceptual_sketch(ax, 311, 'Crossover', [.85, .3], [.3, .85], True)


def selection(ax):
    v6.heading(ax, 274, 65, 'c', 'Useful selection')
    v6.text(ax, 274, 78, 'Clone-adjusted held-out gain (pp)', 7.5, v6.MUTED)
    # The two discovery/test lines make the estimator identifiable even after
    # its original upper method diagram gives way to the conceptual insight.
    v6.text(ax, 274, 91, '2 repeats: freeze per-task + best fixed', 7.5, v6.MUTED)
    v6.text(ax, 274, 101, 'Test 3rd: gain G · rotate 3 folds', 7.5, v6.MUTED)
    v6.text(ax, 274, 113, 'D = G(gen) − G(clone)', 7.5, v6.BLUE)
    stats = v6.D['primary']['paired_difference']
    lo, hi = [value * 100 for value in stats['D_ci95']]
    value = stats['D_real_minus_clone'] * 100
    v6.text(ax, 388, 111, f'{value:+.2f}'.replace('-', '−'),
            10, v6.BLUE, 'bold', 'right')
    # Endpoint labels and the null reference replace redundant full-axis ticks.
    # The interval remains linear in pp, and its point estimate is positioned
    # numerically from the frozen source, not adjusted for visual emphasis.
    px = lambda p: 285 + (p - lo) / (hi - lo) * 99
    v6.text(ax, 274, 123, '95% CI', 7.5, v6.MUTED)
    v6.line(ax, px(0), 124, px(0), 138, '#93A2AE', .6, ls=(0, (2, 2)))
    v6.line(ax, px(lo), 135, px(hi), 135, v6.BLUE, 1.3)
    for q in (lo, hi):
        v6.line(ax, px(q), 132, px(q), 138, v6.BLUE, .75)
    ax.plot(px(value), 135, marker='D', color=v6.BLUE, markersize=4.1,
            markeredgecolor='white', markeredgewidth=.45, zorder=6)
    v6.text(ax, px(lo), 140, f'{lo:+.2f}'.replace('-', '−'),
            7.5, v6.MUTED, ha='center')
    v6.text(ax, px(0), 140, '0', 7.5, v6.MUTED, ha='center')
    v6.text(ax, px(hi), 140, f'{hi:+.2f}', 7.5, v6.MUTED, ha='right')
    v6.text(ax, 331, 151, 'Specialization unresolved', 8,
            weight='bold', ha='center')
    v6.line(ax, 274, 162, 388, 162, v6.RULE, .45)
    v6.lock(ax, 275, 165)
    v6.text(ax, 286, 165, 'Frozen feature selector', 8, weight='bold')
    v6.arrow(ax, (276, 187), (283, 187), v6.BLUE)
    v6.text(ax, 286, 181, 'Baseline', 7.5, v6.BLUE, 'bold')
    policy = v6.D['selector']
    v6.text(ax, 318, 181,
            f'({policy["choices_on_subset"]["bare"]}/{v6.D["n_tasks"]})',
            7.5, v6.MUTED)
    v6.text(ax, 388, 180, f'{policy["gain_vs_bare_pp"]:.2f} pp',
            9, weight='bold', ha='right')
    v6.text(ax, 388, 165, 'gain', 7.5, v6.MUTED, ha='right')


def draw():
    fig, ax = v6.canvas()
    v6.study(ax)
    crossover(ax)
    v6.line(ax, 8, 60, 388, 60, '#BECBD4', .65)
    v6.coverage(ax)
    v6.repeatability(ax)
    selection(ax)
    v6.line(ax, 134, 67, 134, 194, v6.RULE, .45)
    v6.line(ax, 267, 67, 267, 194, v6.RULE, .45)
    return fig
