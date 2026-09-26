"""A: conservative v6 refinement, with a larger illustration and lighter method strip."""
import build_v6 as v6
from v7_common import *


def draw():
    fig, ax = canvas()
    text(ax, 8, 3, f'{D["n_tasks"]} complete MATH-500 tasks · 3 repeats/slot', color=MUTED)
    art(ax, 32, 10, 146)
    mark(ax, 9, 27)
    text(ax, 15, 21, '8 generated', color=TEAL, bold=True)
    text(ax, 15, 32, '+ baseline', color=MUTED)
    mark(ax, 168, 27, clone=True)
    text(ax, 174, 21, '9 identical', color=AMBER, bold=True)
    text(ax, 174, 32, 'baseline slots', color=MUTED)

    text(ax, 221, 4, '3-fold repeat validation', 8, bold=True)
    for j in range(3):
        text(ax, 227+j*15, 17, f'R{j+1}', color=MUTED, ha='center')
    for i in range(3):
        for j in range(3):
            x, y = 220+j*15, 29+i*9
            held = i == j
            box(ax, x, y, 13, 8, BPALE if held else 'white',
                BLUE if held else RULE, radius=1, lw=.45)
            if held:
                text(ax, x+6.5, y+4, 'test', color=BLUE, ha='center', va='center')
    arrow(ax, (266, 36), (276, 36), BLUE)
    box(ax, 280, 18, 108, 22, '#F7F9FB', RULE)
    text(ax, 334, 20, '2 repeats: freeze choices', bold=True, ha='center')
    text(ax, 334, 30, 'per-task + best fixed member', color=MUTED, ha='center')
    arrow(ax, (334, 40), (334, 45), BLUE)
    box(ax, 280, 45, 108, 12, 'white', '#B8CBD8')
    text(ax, 334, 46.5, 'Held-out repeat: gain G', color=BLUE, ha='center')
    arrow(ax, (203, 51), (216, 51), MUTED, .65, 5)
    line(ax, 8, 60, 388, 60, '#BECBD4', .6)

    # Preserve v6's quantitative encodings exactly. No manuscript/archived
    # outputs are written by these drawing functions.
    v6.coverage(ax)
    v6.repeatability(ax)
    v6.selection(ax)
    # Shorter separators reduce the visual weight of the three-column frame.
    line(ax, 134, 78, 134, 142, RULE, .45)
    line(ax, 267, 78, 267, 142, RULE, .45)
    return fig
