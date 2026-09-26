"""V7 C: an illustrated evidence board with four deliberately unequal panels."""
from v7_common import *


def study(ax):
    panel_label(ax, 8, 4, 'a', 'Matched programs and rolls')
    text(ax, 8, 17, '386 complete MATH-500 tasks · 3 repeats/slot', color=MUTED)
    art(ax, 11, 24, 168)
    mark(ax, 12, 89)
    text(ax, 19, 84, '8 generated + baseline', color=TEAL, bold=True)
    mark(ax, 101, 89, clone=True)
    text(ax, 108, 84, '9 identical baseline slots', color=AMBER, bold=True)


def coverage(ax):
    panel_label(ax, 198, 4, 'b', 'Coverage opportunities')
    text(ax, 198, 17, 'Oracle · execution-matched', color=MUTED)
    x0, x1, y0, y1 = 219, 319, 43, 71
    px = lambda v: x0+(v-3)/24*(x1-x0)
    py = lambda v: y1-(v-98.2)/.6*(y1-y0)
    for v in (98.2, 98.5, 98.8):
        line(ax, x0, py(v), x1, py(v), GRID, .45)
        text(ax, x0-4, py(v), f'{v:.1f}', color=MUTED, ha='right', va='center')
    line(ax, x0, y0, x0, y1, MUTED, .45)
    line(ax, x0, y1, x1, y1, MUTED, .45)
    for v in (3, 9, 18, 27):
        line(ax, px(v), y1, px(v), y1+2, MUTED, .4)
        text(ax, px(v), y1+4, str(v), color=MUTED, ha='center')
    xs = [px(row['executions']) for row in D['replay']]
    for key, clone in [('clone_oracle', True), ('panel_oracle', False)]:
        ys = [py(row[key]*100) for row in D['replay']]
        ax.plot(xs, ys, color=AMBER if clone else TEAL, lw=1,
                ls=(0, (2, 1.5)) if clone else '-',
                marker='s' if clone else 'o', markersize=2.6,
                markerfacecolor='white' if clone else TEAL,
                markeredgewidth=.6, zorder=4 if clone else 3)
    final = D['replay'][-1]
    assert final['panel_oracle'] == final['clone_oracle']
    text(ax, 265, 29, f'At 27: {final["panel_oracle"]*100:.2f}% both',
         size=8, bold=True, ha='center')
    text(ax, 269, 87, 'Harness executions', color=MUTED, ha='center')
    line(ax, 329, 20, 329, 92, RULE, .45)
    text(ax, 362, 18, 'Headroom (pp)', color=MUTED, ha='center')
    for y, key, clone in [(47, 'eval_real', False), (70, 'eval_clone', True)]:
        v = D['repeat_plugin'][key]['headroom_pp']
        c = AMBER if clone else TEAL
        mark(ax, 337, y, clone, 3)
        ax.add_patch(Rectangle((344, y-2.6), v*16, 5.2,
                               facecolor=c, edgecolor='none'))
        if clone:
            ax.add_patch(Rectangle((344, y-2.6), v*16, 5.2,
                facecolor='none', edgecolor='white', lw=0, hatch='////'))
        text(ax, 362, y-16, f'{v:.2f}', 9, c, bold=True, ha='center')
    line(ax, 344, 40, 344, 75, MUTED, .45)
    text(ax, 362, 87, 'Repeat-mean', color=MUTED, ha='center')


def repeatability(ax):
    panel_label(ax, 8, 104, 'c', 'Repeatable scored differences')
    text(ax, 8, 118, 'Residual r · 95% CI', color=MUTED)
    px = lambda v: 17+(v+.1)/1.1*79
    for v in (0, .5, 1):
        line(ax, px(v), 134, px(v), 171, GRID, .45)
        text(ax, px(v), 174, f'{v:g}', color=MUTED, ha='center')
    for key, y, clone in [('eval_real', 145, False), ('eval_clone', 167, True)]:
        s = D['repeatability'][key]
        v = s['mean_pearson_residualized']
        lo, hi = s['mean_pearson_residualized_ci95']
        c = AMBER if clone else TEAL
        line(ax, px(lo), y, px(hi), y, c, 1.25)
        for q in (lo, hi):
            line(ax, px(q), y-2.5, px(q), y+2.5, c, .75)
        mark(ax, px(v), y, clone, 4)
        text(ax, px(v), y-15, f'{v:.3f}', 9, c, bold=True, ha='center')
    line(ax, 104, 120, 104, 183, RULE, .45)
    text(ax, 112, 118, 'Persistent vs baseline', color=MUTED)
    text(ax, 112, 131, '100 losses', 8.5, LOSS, bold=True)
    nloss = D['repeatability']['eval_real']['all_repeat_patterns']['loss_tasks']
    nwin = D['repeatability']['eval_real']['all_repeat_patterns']['win_tasks']
    assert nloss == 100 and nwin == 1
    for i in range(nloss):
        x, y = 112+(i%20)*3.3, 144+(i//20)*3.3
        ax.add_patch(Rectangle((x, y), 2.25, 2.25, facecolor=LOSS, edgecolor='none'))
    ax.add_patch(Rectangle((112, 168), 2.25, 2.25, facecolor=TEAL, edgecolor='none'))
    text(ax, 119, 164, '1 win*', 8.5, TEAL, bold=True)
    text(ax, 112, 176, 'Tasks · any member · 3/3', color=MUTED)
    text(ax, 8, 188, '*Extraction-sensitive', color=MUTED)


def selection(ax):
    panel_label(ax, 198, 104, 'd', 'Useful selection')
    for row in range(3):
        for col in range(3):
            held = row == col
            box(ax, 199+col*6, 119+row*6, 5, 5,
                BLUE if held else '#E4EDF3', BLUE if held else '#BCD0DD', .5, .35)
    arrow(ax, (218, 127), (227, 127), BLUE, .6, 4)
    text(ax, 233, 117, '2 repeats: freeze per-task + best fixed', color=MUTED)
    text(ax, 233, 130, 'Test 3rd repeat · rotate all 3 folds', color=MUTED)
    s = D['primary']['paired_difference']
    lo, hi = [v*100 for v in s['D_ci95']]
    v = s['D_real_minus_clone']*100
    text(ax, 198, 145, f'D = {v:+.2f} pp'.replace('-', '−'), 8.5, BLUE, bold=True)
    text(ax, 388, 146, f'95% CI [{lo:+.2f}, {hi:+.2f}]'.replace('-', '−'),
         color=MUTED, ha='right')
    px = lambda q: 211+(q+2)/4*79
    line(ax, px(0), 157, px(0), 169, '#93A2AE', .6, ls=(0, (2, 2)))
    line(ax, px(-2), 166, px(2), 166, MUTED, .45)
    line(ax, px(lo), 160, px(hi), 160, BLUE, 1.3)
    for q in (lo, hi):
        line(ax, px(q), 157, px(q), 163, BLUE, .75)
    ax.plot(px(v), 160, marker='D', color=BLUE, markersize=4.1,
            markeredgecolor='white', markeredgewidth=.45, zorder=6)
    for tick in (-2, 0, 2):
        text(ax, px(tick), 168, str(tick).replace('-', '−'), color=MUTED, ha='center')
    text(ax, 342, 159, 'Specialization unresolved', 8, bold=True, ha='center')
    text(ax, 342, 170, 'Clone-adjusted held-out gain', color=MUTED, ha='center')
    line(ax, 198, 182, 388, 182, RULE, .45)
    policy = D['selector']
    text(ax, 198, 187, f'Frozen feature selector → baseline {policy["choices_on_subset"]["bare"]}/386', color=MUTED)
    text(ax, 388, 187, f'{policy["gain_vs_bare_pp"]:.2f} pp gain', 8, bold=True, ha='right')


def draw():
    # Export happens after returning: retain Type42 font settings for savefig.
    plt.rcParams.update(STYLE)
    fig, ax = canvas()
    study(ax)
    coverage(ax)
    repeatability(ax)
    selection(ax)
    line(ax, 8, 99, 388, 99, '#BECBD4', .65)
    line(ax, 190, 4, 190, 95, RULE, .55)
    line(ax, 190, 104, 190, 194, RULE, .55)
    return fig


if __name__ == '__main__':
    import fitz
    fig = draw()
    fig.savefig('/tmp/v7_c_board.pdf', metadata={'Title': '', 'CreationDate': None, 'ModDate': None})
    with fitz.open('/tmp/v7_c_board.pdf') as doc:
        doc[0].get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False).save('/tmp/v7_c_board.png')
