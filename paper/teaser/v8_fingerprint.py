"""V6 derivative: same-code control illustrated with recorded repeat scores.

Only ``draw()`` creates figure content; the version exporter owns output files.
The paired fingerprint is the observed, deliberately illustrative task #138,
not a representative sample and not the data from which residual r is computed.
All 54 scores are read from the frozen repeat tensors.  The program-card motifs
are schematic, not claims about the actual programs' control flow.
"""
from __future__ import annotations

import hashlib

import numpy as np
from matplotlib.patches import Circle, Polygon, Rectangle

import build_v6 as v6


TASK_ID = 'math500_split#138'
MATRIX_SOURCES = {
    'eval_real.npz': '57c98d81cb00cc2fa3cf47cfa76649be6b5f8bf556d3fa73981f93430188a9c1',
    'eval_clone.npz': 'fb76655eaa7f923e529fa484f5ecb2fb3389aff9cd7d29d49ee31ead75363feb',
}
REAL_MEMBERS = [
    'bare', 'gsm_deepseek_s0_g3', 'gsm_ernie_s0_g3', 'gsm_glm_s0_g6',
    'gsm_kimi_s0_g3', 'gsm_kimi_s0_g4', 'gsm_minimax_s0_g0',
    'gsm_minimax_s0_g3', 'gsm_qwen_s0_g5',
]
CLONE_MEMBERS = [f'clone-c{i}' for i in range(1, 10)]


def recorded_fingerprint():
    """Return member × repeat binary scores with all identity axes checked."""
    results = []
    task_axis = None
    for name, expected_members in zip(MATRIX_SOURCES, (REAL_MEMBERS, CLONE_MEMBERS)):
        path = v6.SOURCE.parent / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == MATRIX_SOURCES[name]
        with np.load(path, allow_pickle=False) as data:
            assert data['stack'].shape == (3, 9, v6.D['n_tasks'])
            assert data['members'].tolist() == expected_members
            assert data['repeats'].tolist() == [1, 2, 3]
            tasks = data['tasks'].tolist()
            assert len(tasks) == len(set(tasks)) == v6.D['n_tasks']
            assert task_axis is None or task_axis == tasks
            task_axis = tasks
            assert np.isin(data['stack'], (0, 1)).all()
            results.append(data['stack'][:, :, tasks.index(TASK_ID)].T.astype(int))
    # Freeze the displayed interpretation as well as the source bytes.
    assert [''.join(map(str, row)) for row in results[0]] == [
        '111', '000', '000', '000', '101', '010', '000', '000', '000']
    assert [''.join(map(str, row)) for row in results[1]] == [
        '101', '111', '111', '101', '111', '110', '011', '011', '010']
    return results


def code_card(ax, x, y, color, motif=0):
    """A tiny native-vector document, with a schematic code/flow motif."""
    w, h = 8.6, 16.0
    edge = color
    ax.add_patch(Polygon(
        [(x, y), (x+w-2.2, y), (x+w, y+2.2), (x+w, y+h), (x, y+h)],
        closed=True, facecolor='white', edgecolor=edge, linewidth=.55,
        joinstyle='round'))
    v6.line(ax, x+w-2.2, y, x+w-2.2, y+2.2, edge, .45)
    v6.line(ax, x+w-2.2, y+2.2, x+w, y+2.2, edge, .45)
    ax.add_patch(Rectangle((x+.7, y+3.8), 1.0, h-5.0,
                           facecolor=color, edgecolor='none', alpha=.18))
    if motif == 0:
        # Baseline and all nine same-code slots share this exact motif.
        for yy, right in ((5.2, 6.5), (8.2, 5.5), (11.2, 6.5)):
            v6.line(ax, x+2.3, y+yy, x+right, y+yy, color, .65)
    else:
        # Distinct motifs suggest different programs, not measured topology.
        variant = (motif - 1) % 4
        v6.line(ax, x+2.3, y+5.1, x+6.3, y+5.1, color, .6)
        if variant in (0, 2):
            v6.line(ax, x+3.0, y+7.5, x+3.0, y+12.5, color, .6)
            v6.line(ax, x+3.0, y+8.4, x+6.1, y+8.4, color, .6)
            v6.line(ax, x+3.0, y+11.5, x+5.2+(motif > 4), y+11.5, color, .6)
        else:
            for yy, left, right in ((8.1, 3.4, 6.3), (11.1, 2.3, 5.5)):
                v6.line(ax, x+left, y+yy, x+right, y+yy, color, .6)
        if variant in (2, 3):
            ax.add_patch(Circle((x+6.3, y+13.2), .65,
                                facecolor=color, edgecolor='none'))


def score(ax, x, y, value, color, radius=1.4):
    """Filled = scored correct; hollow = scored wrong, also readable in gray."""
    ax.add_patch(Circle((x, y), radius, facecolor=color if value else 'white',
                        edgecolor=color, linewidth=.35))


def study(ax):
    """Two controlled program arms, each with its complete 9 × 3 fingerprint."""
    generated, clones = recorded_fingerprint()
    v6.text(ax, 8, 3, '386 complete MATH tasks · 3 fresh repeats', 7.5, v6.MUTED)
    v6.text(ax, 8, 14, '8 generated + baseline', 7.5, v6.TEAL, 'bold')
    v6.text(ax, 116, 14, '9 identical baseline slots', 7.5, v6.AMBER, 'bold')
    for origin, values, clone_arm in ((8, generated, False), (116, clones, True)):
        arm_color = v6.AMBER if clone_arm else v6.TEAL
        for member, outcomes in enumerate(values):
            x = origin + member * 11.2
            # The first generated-arm card is its baseline; the remaining
            # eight have varied motifs.  All clone motifs match baseline.
            color = arm_color if clone_arm or member else v6.INK
            motif = 0 if clone_arm else member
            code_card(ax, x, 25, color, motif)
            for repeat, value in enumerate(outcomes):
                score(ax, x+.9+repeat*3.4, 45.1, value, color)
    v6.text(ax, 8, 50.5, 'Selected example #138 · R1–R3', 7.5, v6.MUTED)
    score(ax, 114, 54.0, 1, v6.INK, 1.35)
    v6.text(ax, 119, 50.5, 'correct', 7.5, v6.MUTED)
    score(ax, 164, 54.0, 0, v6.INK, 1.35)
    v6.text(ax, 169, 50.5, 'wrong', 7.5, v6.MUTED)


def draw():
    # Late import permits the sibling implementation to be developed
    # independently.  Its method strip stays entirely in x221..388.
    from v8_calibrated import protocol, selection
    fig, ax = v6.canvas()
    study(ax)
    protocol(ax)
    v6.line(ax, 8, 60, 388, 60, '#BECBD4', .65)
    v6.coverage(ax)
    v6.repeatability(ax)
    selection(ax)
    v6.line(ax, 134, 67, 134, 194, v6.RULE, .45)
    v6.line(ax, 267, 67, 267, 194, v6.RULE, .45)
    return fig
