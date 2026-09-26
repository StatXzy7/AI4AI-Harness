#!/usr/bin/env python3
"""Evidence-rich, title-free teasers; writes only output/v3/."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle
from matplotlib.textpath import TextToPath

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'artifacts/common386_20260926/analysis.json'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == (
    '253a2587fa67d3be8e830a22582497ec7c26ba6ee67db10ef85b5735cfa2ca21'
), 'This version is tied to the reviewed 26 September 2026 evidence snapshot.'
D = json.loads(SOURCE.read_text())
OUT = HERE / 'output/v3'
OUT.mkdir(parents=True, exist_ok=True)
FONTS = HERE / 'assets/fonts'
for p in FONTS.glob('SourceSans3-*.ttf'):
    font_manager.fontManager.addfont(str(p))
REG = FontProperties(fname=FONTS / 'SourceSans3-Regular.ttf')
SEMI = FontProperties(fname=FONTS / 'SourceSans3-Semibold.ttf')
ITAL = FontProperties(fname=FONTS / 'SourceSans3-It.ttf')

W, H = 396, 269
INK = '#24333F'
MUTED = '#596775'
RULE = '#D6DDE2'
GRID = '#E8EDF0'
TEAL = '#087C83'
AMBER = '#AC6B16'
BLUE = '#3D587A'
LOSS = '#AF625E'
TPALE, APALE = '#EEF7F6', '#FCF5EA'

plt.rcParams.update({
    'font.family': REG.get_name(), 'font.size': 7,
    'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none',
    'axes.unicode_minus': True, 'savefig.facecolor': 'white',
    'mathtext.fontset': 'stix',
})


def text(ax, x, y, s, size=7, color=INK, weight='normal', ha='left', va='top', **kw):
    fp = SEMI if weight == 'bold' else ITAL if weight == 'italic' else REG
    return ax.text(x, y, s, fontsize=size, fontproperties=fp, color=color,
                   ha=ha, va=va, linespacing=1.07, **kw)


def equation(ax, x, y):
    # Subscripts remain Source Sans, with explicit spacing and readable size.
    parts = [('Compare arms: ', 7, 0, 'normal'), ('D', 7, 0, 'italic'),
             (' = ', 7, 0, 'normal'), ('G', 7, 0, 'italic'),
             ('gen', 6.1, 2.4, 'normal'), (' − ', 7, 0, 'normal'),
             ('G', 7, 0, 'italic'), ('clone', 6.1, 2.4, 'normal')]
    metric = TextToPath()
    for s, size, dy, weight in parts:
        text(ax, x, y+dy, s, size, MUTED, weight)
        fp = (ITAL if weight == 'italic' else REG).copy()
        fp.set_size(size)
        x += metric.get_text_width_height_descent(s, fp, ismath=False)[0]


def line(ax, x1, y1, x2, y2, color=RULE, lw=.55, **kw):
    ax.plot([x1, x2], [y1, y2], color=color, lw=lw,
            solid_capstyle='round', clip_on=False, **kw)


def box(ax, x, y, w, h, fill='white', edge=RULE, radius=2, lw=.55):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
        boxstyle=f'round,pad=0,rounding_size={radius}',
        facecolor=fill, edgecolor=edge, linewidth=lw))


def arrow(ax, a, b, color=MUTED, lw=.7, scale=6):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle='-|>', mutation_scale=scale,
                               color=color, linewidth=lw, shrinkA=0, shrinkB=0))


def mark(ax, x, y, clone=False, size=3.5, color=None):
    ax.plot(x, y, marker='s' if clone else 'o', markersize=size,
            color=color or (AMBER if clone else TEAL),
            markeredgecolor='white', markeredgewidth=.35, zorder=7)


def heading(ax, x, y, letter, label):
    text(ax, x, y, letter, 8.6, BLUE, 'bold')
    text(ax, x+12, y, label, 8.6, weight='bold')


def canvas():
    fig = plt.figure(figsize=(W/72, H/72), facecolor='white')
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, W), ylim=(H, 0))
    ax.set_axis_off()
    return fig, ax


def program(ax, x, y, k, clone=False):
    """Conceptual program icons, deliberately not empirical execution traces."""
    c = AMBER if clone else INK if k == 8 else TEAL
    box(ax, x, y, 10.8, 20, APALE if clone else TPALE if k < 8 else '#F0F2F4', c, 1.2, .5)
    if clone or k == 8:
        pts, edges = [(5.4, 4), (5.4, 10), (5.4, 16)], [(0, 1), (1, 2)]
    else:
        motifs = [
            ([(5.4, 4), (2.8, 10), (8, 10), (5.4, 16)], [(0, 1), (0, 2), (1, 3), (2, 3)]),
            ([(3, 4), (3, 10), (8, 10), (8, 16)], [(0, 1), (1, 2), (2, 3)]),
            ([(5.4, 4), (2.8, 10), (8, 10), (2.8, 16)], [(0, 1), (0, 2), (1, 3)]),
            ([(3, 4), (8, 4), (8, 16), (3, 16)], [(0, 1), (1, 2), (2, 3), (3, 0)]),
            ([(3, 4), (8, 10), (3, 16)], [(0, 1), (1, 2), (2, 0)]),
            ([(5.4, 4), (2.8, 16), (8, 16)], [(0, 1), (0, 2)]),
            ([(3, 4), (8, 4), (5.4, 10), (5.4, 16)], [(0, 2), (1, 2), (2, 3)]),
            ([(3, 4), (3, 10), (8, 10), (8, 16)], [(0, 1), (1, 2), (2, 3), (3, 1)]),
        ]
        pts, edges = motifs[k]
    for i, j in edges:
        line(ax, x+pts[i][0], y+pts[i][1], x+pts[j][0], y+pts[j][1], c, .5)
    for xx, yy in pts:
        ax.add_patch(Circle((x+xx, y+yy), .83, facecolor=c, edgecolor='none'))


def study(ax, illustrated=False):
    heading(ax, 8, 5, 'a', 'Programs × repeats')
    if illustrated:
        art = mpimg.imread(HERE / 'assets/programs_and_rolls.png')
        aw = 184
        ah = aw*art.shape[0]/art.shape[1]
        ax.imshow(art, extent=(5, 5+aw, 18+ah, 18),
                  interpolation='none', resample=False, aspect='equal', zorder=-1)
        mark(ax, 15, 20.5)
        text(ax, 21, 16, '8 generated + baseline', 6.7, TEAL, 'bold')
        mark(ax, 114, 20.5, clone=True)
        text(ax, 120, 16, '9 same-code slots', 6.7, AMBER, 'bold')
    else:
        mark(ax, 11, 29)
        text(ax, 17, 23, 'Generated', 7.3, TEAL, 'bold')
        text(ax, 17, 34, '8 + baseline', 6.7, MUTED)
        mark(ax, 11, 56, clone=True)
        text(ax, 17, 50, 'Same code', 7.3, AMBER, 'bold')
        text(ax, 17, 61, '9 baseline slots', 6.7, MUTED)
        for i in range(9):
            program(ax, 77+i*12.5, 23, i)
            program(ax, 77+i*12.5, 50, i, clone=True)
    text(ax, 8, 82, '386 common MATH-500 tasks · 3 repeats/slot', 7, MUTED)


def protocol(ax):
    heading(ax, 207, 5, 'b', 'Discover → freeze → validate')
    # All three rotations are drawn. The dark held-out cell moves each fold;
    # the other two cells are discovery repeats, never test outcomes.
    for j in range(3):
        text(ax, 218+j*15, 21, f'R{j+1}', 6.6, MUTED, ha='center')
    for i in range(3):
        for j in range(3):
            x, y = 211+j*15, 33+i*13
            held = i == j
            box(ax, x, y, 13, 10, BLUE if held else '#E4EDF3',
                BLUE if held else '#BCD0DD', 1, .4)
            if held:
                text(ax, x+6.5, y+5, 'test', 6.1, 'white',
                     ha='center', va='center')
    arrow(ax, (261, 50), (275, 50), BLUE)
    box(ax, 283, 25, 100, 24, '#E4EDF3', '#BCD0DD')
    text(ax, 333, 29, 'Discovery ×2: freeze choices', 7.1, ha='center', weight='bold')
    text(ax, 333, 39, 'per-task member + best fixed', 6.2, MUTED, ha='center')
    arrow(ax, (333, 49), (333, 57), BLUE)
    box(ax, 283, 57, 100, 19, BLUE, BLUE)
    text(ax, 333, 61, 'Held-out repeat: gain G', 7.1, 'white', ha='center', weight='bold')
    text(ax, 211, 73, '3 folds', 6.3, MUTED)
    equation(ax, 207, 83)


def coverage(ax):
    heading(ax, 8, 106, 'c', 'Coverage')
    text(ax, 8, 119, 'Oracle · execution-matched', 6.8, MUTED)
    x0, x1, y0, y1 = 29, 125, 141, 201
    px = lambda v: x0+(v-3)/24*(x1-x0)
    py = lambda v: y1-(v-98.2)/.6*(y1-y0)
    for v in (98.2, 98.4, 98.6, 98.8):
        line(ax, x0, py(v), x1, py(v), GRID, .45)
        text(ax, x0-4, py(v), f'{v:.1f}', 6.1, MUTED, ha='right', va='center')
    line(ax, x0, y0, x0, y1, MUTED, .45)
    line(ax, x0, y1, x1, y1, MUTED, .45)
    for v in (3, 9, 18, 27):
        line(ax, px(v), y1, px(v), y1+2, MUTED, .4)
        text(ax, px(v), y1+4, str(v), 6.3, MUTED, ha='center')
    xs = [px(r['executions']) for r in D['replay']]
    for key, clone in [('clone_oracle', True), ('panel_oracle', False)]:
        ys = [py(r[key]*100) for r in D['replay']]
        ax.plot(xs, ys, color=AMBER if clone else TEAL, lw=1.0,
                ls=(0, (2, 1.5)) if clone else '-',
                marker='s' if clone else 'o', markersize=2.6,
                markerfacecolor='white' if clone else TEAL,
                markeredgewidth=.6, zorder=4 if clone else 3)
    text(ax, 8, 130, '%', 6.1, MUTED)
    text(ax, 78, 132, 'At 27: 98.70% both', 7.2, weight='bold', ha='center')
    text(ax, 77, 215, 'Harness executions', 6.4, MUTED, ha='center')
    line(ax, 8, 227, 128, 227, RULE, .45)
    text(ax, 8, 231, 'Repeat-mean oracle headroom · pp', 6.3, MUTED)
    for yy, key, clone in [(247, 'eval_real', False), (259, 'eval_clone', True)]:
        v = D['repeat_plugin'][key]['headroom_pp']
        c = AMBER if clone else TEAL
        mark(ax, 12, yy, clone)
        ax.add_patch(Rectangle((22, yy-2.7), v*28, 5.4,
                               facecolor=c, edgecolor='none'))
        if clone:
            ax.add_patch(Rectangle((22, yy-2.7), v*28, 5.4,
                                   facecolor='none', edgecolor='white', lw=0, hatch='////'))
        text(ax, 123, yy, f'{v:.2f}', 7.5, c, 'bold', 'right', 'center')
    line(ax, 22, 242, 22, 263, MUTED, .45)


def repeatability(ax):
    heading(ax, 141, 106, 'd', 'Repeatability')
    text(ax, 141, 119, 'Residual r · 95% CI', 6.8, MUTED)
    px = lambda v: 153 + (v+.1)/1.1*101
    for v in (0, .5, 1):
        line(ax, px(v), 142, px(v), 180, GRID, .45)
        text(ax, px(v), 183, f'{v:g}', 6.2, MUTED, ha='center')
    for key, yy, clone in [('eval_real', 150, False), ('eval_clone', 173, True)]:
        s = D['repeatability'][key]
        v = s['mean_pearson_residualized']
        lo, hi = s['mean_pearson_residualized_ci95']
        c = AMBER if clone else TEAL
        line(ax, px(lo), yy, px(hi), yy, c, 1.25)
        for q in (lo, hi):
            line(ax, px(q), yy-2.6, px(q), yy+2.6, c, .75)
        mark(ax, px(v), yy, clone, 4)
        text(ax, px(v), yy-15, f'{v:.3f}', 8, c, 'bold', 'center')
    line(ax, 141, 197, 261, 197, RULE, .45)
    text(ax, 141, 201, 'Persistent scores vs baseline', 6.7, MUTED)
    text(ax, 141, 212, 'Any member · 3/3 repeats · tasks', 6.2, MUTED)
    # A unit square represents one task. Counts are never rounded or rescaled.
    nloss = D['repeatability']['eval_real']['all_repeat_patterns']['loss_tasks']
    nwin = D['repeatability']['eval_real']['all_repeat_patterns']['win_tasks']
    for i in range(nloss):
        x, y = 142 + (i % 20)*3.55, 225+(i//20)*3.55
        ax.add_patch(Rectangle((x, y), 2.5, 2.5, facecolor=LOSS, edgecolor='none'))
    text(ax, 218, 224, f'{nloss}', 10.5, LOSS, 'bold')
    text(ax, 218, 236, 'losses', 6.7, MUTED)
    ax.add_patch(Rectangle((142, 247), 2.5, 2.5, facecolor=TEAL, edgecolor='none'))
    text(ax, 149, 243, f'{nwin} win*', 7.2, TEAL, 'bold')
    text(ax, 141, 256, '*Extraction-sensitive', 6.4, MUTED)


def lock(ax, x, y, color=BLUE):
    box(ax, x, y+4, 7, 6, '#E4EDF3', color, 1, .5)
    ax.add_patch(matplotlib.patches.Arc((x+3.5, y+4), 4, 6,
                                       theta1=0, theta2=180, color=color, lw=.6))
    ax.add_patch(Circle((x+3.5, y+7), .6, facecolor=color, edgecolor='none'))


def selection(ax):
    heading(ax, 274, 106, 'e', 'Useful selection')
    text(ax, 274, 119, 'Clone-adjusted held-out gain · pp', 6.5, MUTED)
    px = lambda v: 281 + (v+2)/4*98
    line(ax, px(0), 139, px(0), 181, '#93A2AE', .6, ls=(0, (2, 2)))
    line(ax, px(-2), 170, px(2), 170, MUTED, .45)
    for v in (-2, -1, 0, 1, 2):
        line(ax, px(v), 170, px(v), 172, MUTED, .4)
        text(ax, px(v), 176, str(v).replace('-', '−'), 6.2, MUTED, ha='center')
    s = D['primary']['paired_difference']
    lo, hi = [v*100 for v in s['D_ci95']]
    v = s['D_real_minus_clone']*100
    line(ax, px(lo), 153, px(hi), 153, BLUE, 1.3)
    for q in (lo, hi):
        line(ax, px(q), 150, px(q), 156, BLUE, .75)
    ax.plot(px(v), 153, marker='D', color=BLUE, markersize=4.1,
            markeredgecolor='white', markeredgewidth=.45, zorder=6)
    text(ax, px(v), 136, f'{v:+.2f}'.replace('-', '−'), 9, BLUE, 'bold', 'center')
    text(ax, 331, 190, '95% CI [−1.45, +0.95]', 6.5, MUTED, ha='center')
    text(ax, 331, 204, 'Complementarity unresolved', 7.5, weight='bold', ha='center')
    line(ax, 274, 221, 388, 221, RULE, .45)
    lock(ax, 275, 230)
    text(ax, 286, 229, 'Frozen feature selector', 7, weight='bold')
    arrow(ax, (282, 249), (296, 249), BLUE)
    text(ax, 300, 243, 'Baseline', 7, BLUE, 'bold')
    text(ax, 300, 254, '386 / 386 tasks', 6.3, MUTED)
    text(ax, 388, 243, '0.00 pp', 8.2, weight='bold', ha='right')
    text(ax, 388, 255, 'gain', 6.3, MUTED, ha='right')


def draw(illustrated=False):
    fig, ax = canvas()
    study(ax, illustrated)
    protocol(ax)
    line(ax, 197, 6, 197, 89, RULE, .55)
    line(ax, 8, 98, 388, 98, '#BECBD4', .65)
    coverage(ax)
    repeatability(ax)
    selection(ax)
    line(ax, 134, 110, 134, 262, RULE, .45)
    line(ax, 267, 110, 267, 262, RULE, .45)
    return fig


def inspect(path):
    with fitz.open(path) as doc:
        p = doc[0]
        spans = [s for b in p.get_text('dict')['blocks']
                 for l in b.get('lines', []) for s in l['spans']]
        outside = [s['text'] for s in spans if not p.rect.contains(fitz.Rect(s['bbox']))]
        assert not outside, outside
        embedded = all(doc.extract_font(f[0])[3] for f in p.get_fonts(full=True))
        assert embedded
        txt = p.get_text()
        for required in ['386', '2.33', '2.16', '0.789', '0.006', '0.00',
                         '98.70', '100', '1 win', '−0.26', '−1.45', '+0.95',
                         'unresolved', 'Extraction-sensitive']:
            assert required in txt, (path, required)
        p.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False).save(path.with_suffix('.preview.png'))
        p.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csGRAY, alpha=False).save(
            path.with_suffix('.grayscale.png'))
        return {'file': path.name, 'page_count': len(doc), 'width_pt': p.rect.width,
                'height_pt': p.rect.height, 'visible_word_count': len(p.get_text('words')),
                'minimum_font_pt': round(min(s['size'] for s in spans), 2),
                'fonts': sorted(set(s['font'] for s in spans)),
                'raster_images': len(p.get_images()), 'embedded_fonts': bool(embedded),
                'text_within_page': True, 'global_title': False,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    paths, outputs = [], []
    for name, illustrated in [('academic', False), ('illustrated', True)]:
        fig = draw(illustrated)
        path = OUT / f'teaser_{name}.pdf'
        fig.savefig(path, metadata={'Title': '', 'Author': '',
                                   'Subject': 'MATH-500 controls, repeatability, and selection',
                                   'CreationDate': None, 'ModDate': None})
        fig.savefig(path.with_suffix('.svg'), metadata={'Date': None})
        plt.close(fig)
        outputs.append(inspect(path))
        paths.append(path)
    with fitz.open() as both:
        for p in paths:
            with fitz.open(p) as doc:
                both.insert_pdf(doc)
        both.save(OUT / 'teaser_both_styles.pdf')
    prior = json.loads((OUT / 'previous_versions_manifest.json').read_text())
    assert all(hashlib.sha256((HERE / p).read_bytes()).hexdigest() == h
               for p, h in prior.items()), 'A previous version changed'
    manifest = {
        'version': 'v3', 'source': str(SOURCE.relative_to(ROOT)),
        'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'base_commit': '922c914cc7ce218e43b5a7114e582cf35632d253',
        'data_transformations': ['Source proportions × 100 for percent and pp.',
                                 'Display rounding only. All nine replay budgets shown.',
                                 'One persistent-loss square per task; no invented data.'],
        'schematics': 'Program motifs and repeat-fold cells are conceptual protocol diagrams.',
        'fonts': 'Adobe Source Sans 3 Regular, Semibold, and Italic; SIL OFL 1.1.',
        'artwork': 'Unmodified v1 image in illustrated PDF only.',
        'previous_version_files_unchanged': len(prior),
        'outputs': outputs,
    }
    (OUT / 'provenance.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (OUT / 'validation.json').write_text(json.dumps({
        'source_values_checked': True, 'previous_versions_unchanged': True,
        'outputs': outputs}, indent=2)+'\n')
    print(json.dumps(outputs, indent=2))


if __name__ == '__main__':
    main()
