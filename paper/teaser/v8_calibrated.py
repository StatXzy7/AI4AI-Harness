"""A substantive v6 refinement: clone calibration and persistent-score semantics.

Drawing only: this module never writes into an archived output directory.
The program illustration and four quantitative panels are inherited from v6.
"""
import build_v6 as v6


def protocol(ax):
    """Both study arms pass through the same frozen held-out evaluation."""
    v6.text(ax, 221, 4, 'Held-out calibration · rotate 3 folds', 8, weight='bold')

    # The same two colored arms enter both operations. They are not gains
    # inferred by subtracting the repeat-mean headroom bars below.
    for y, clone in ((24, False), (35, True)):
        color = v6.AMBER if clone else v6.TEAL
        v6.mark(ax, 223, y, clone, 3)
        v6.arrow(ax, (226, y), (235, y), color, .75, 4)
    v6.box(ax, 236, 17, 99, 24, '#F2F6F8', '#BCD0DD', 2, .55)
    v6.text(ax, 285.5, 19, '2 repeats: freeze choices', 7.5,
            weight='bold', ha='center')
    v6.text(ax, 285.5, 30, 'per-task + best fixed member', 7.5,
            v6.MUTED, ha='center')
    for y, clone in ((24, False), (35, True)):
        v6.arrow(ax, (335, y), (341, y),
                 v6.AMBER if clone else v6.TEAL, .75, 4)
    v6.box(ax, 342, 17, 46, 24, '#F2F6F8', '#BCD0DD', 2, .55)
    v6.text(ax, 365, 19, 'Test: gain G', 7.5, weight='bold', ha='center')
    v6.text(ax, 365, 30, '3rd repeat', 7.5, v6.MUTED, ha='center')
    v6.arrow(ax, (365, 41), (365, 45), v6.BLUE, .6, 4)

    # Baseline-height tokens avoid unreadable equation subscripts. Colors
    # preserve each arm's identity through the clone-adjusted difference.
    v6.box(ax, 221, 45, 167, 12, '#E8EFF5', '#E8EFF5', 2, 0)
    v6.text(ax, 280, 46.6, 'D =', 8, v6.BLUE, 'bold', ha='right')
    v6.text(ax, 284, 46.6, 'G gen', 8, v6.TEAL, 'bold')
    v6.text(ax, 308, 46.6, '−', 8, v6.BLUE, 'bold')
    v6.text(ax, 318, 46.6, 'G clone', 8, v6.AMBER, 'bold')


def _outcome(ax, x, y, correct, color):
    """A vector correctness glyph; neither a font nor a fabricated data cell."""
    if correct:
        v6.line(ax, x-1.25, y, x-.2, y+1.05, color, .8)
        v6.line(ax, x-.2, y+1.05, x+1.6, y-1.4, color, .8)
    else:
        v6.line(ax, x-1.05, y-1.05, x+1.05, y+1.05, color, .8)
        v6.line(ax, x-1.05, y+1.05, x+1.05, y-1.05, color, .8)


def repeatability(ax):
    """V6 correlation, with the direction of persistent scores made visible."""
    v6.heading(ax, 141, 65, 'b', 'Repeatability')
    v6.text(ax, 141, 78, 'Residual r · 95% CI', 7.5, v6.MUTED)
    px = lambda value: 153 + (value+.1)/1.1*101
    for value in (0, .5, 1):
        v6.line(ax, px(value), 92, px(value), 130, v6.GRID, .45)
        v6.text(ax, px(value), 132, f'{value:g}', 7.5,
                v6.MUTED, ha='center')
    for key, y, clone in [('eval_real', 102, False), ('eval_clone', 122, True)]:
        result = v6.D['repeatability'][key]
        value = result['mean_pearson_residualized']
        lo, hi = result['mean_pearson_residualized_ci95']
        color = v6.AMBER if clone else v6.TEAL
        v6.line(ax, px(lo), y, px(hi), y, color, 1.25)
        for end in (lo, hi):
            v6.line(ax, px(end), y-2.6, px(end), y+2.6, color, .75)
        v6.mark(ax, px(value), y, clone, 4)
        v6.text(ax, px(value), y-14, f'{value:.3f}', 9,
                color, 'bold', 'center')

    v6.line(ax, 141, 145, 261, 145, v6.RULE, .45)
    v6.text(ax, 141, 148, 'Persistent tasks · any member', 7.5, v6.MUTED)
    v6.text(ax, 141, 158.5, 'Baseline / member · 3/3 repeats', 7.5, v6.MUTED)
    counts = v6.D['repeatability']['eval_real']['all_repeat_patterns']
    # Preserve v6's honest one-square-per-task visual asymmetry. Equal-size
    # loss/win cards were rejected in review because they obscure 100 versus 1.
    for i in range(counts['loss_tasks']):
        ax.add_patch(v6.Rectangle((142+(i % 20)*3, 171+(i // 20)*3),
                                  2.1, 2.1, facecolor=v6.LOSS, edgecolor='none'))
    v6.text(ax, 207, 170, str(counts['loss_tasks']), 9, v6.LOSS, 'bold')
    v6.text(ax, 224, 172, 'losses', 7.5, v6.MUTED)
    # The small score key explains the loss definition without pretending
    # that every generated member fails or that arrows denote execution.
    for offset in (0, 4, 8):
        _outcome(ax, 210+offset, 183, True, v6.MUTED)
        _outcome(ax, 232+offset, 183, False, v6.LOSS)
    v6.line(ax, 225, 180.5, 225, 185.5, v6.RULE, .6)
    ax.add_patch(v6.Rectangle((142, 191), 2.1, 2.1, facecolor=v6.TEAL, edgecolor='none'))
    v6.text(ax, 147, 188, f'{counts["win_tasks"]} win*', 7.5, v6.TEAL, 'bold')
    v6.text(ax, 177, 188, '*Extraction-sensitive', 7.5, v6.MUTED)


def selection(ax):
    """Keep the v6 result and explicitly name the statistic defined above."""
    v6.selection(ax)
    labels = [artist for artist in ax.texts
              if artist.get_text() == 'Clone-adjusted held-out gain (pp)']
    assert len(labels) == 1
    labels[0].set_text('Clone-adjusted gain D (pp)')


def draw():
    fig, ax = v6.canvas()
    v6.study(ax)
    protocol(ax)
    v6.line(ax, 8, 60, 388, 60, '#BECBD4', .65)
    v6.coverage(ax)
    repeatability(ax)
    selection(ax)
    v6.line(ax, 134, 67, 134, 194, v6.RULE, .45)
    v6.line(ax, 267, 67, 267, 194, v6.RULE, .45)
    return fig
