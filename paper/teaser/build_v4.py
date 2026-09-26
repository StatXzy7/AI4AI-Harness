#!/usr/bin/env python3
"""Shallow, manuscript-sized teasers; writes only output/v4/."""
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
OUT = HERE / 'output/v4'
OUT.mkdir(parents=True, exist_ok=True)
FONTS = HERE / 'assets/fonts'
for p in FONTS.glob('STIXGeneral*.ttf'):
    font_manager.fontManager.addfont(str(p))
REG = FontProperties(fname=FONTS / 'STIXGeneral.ttf')
SEMI = FontProperties(fname=FONTS / 'STIXGeneralBol.ttf')
ITAL = FontProperties(fname=FONTS / 'STIXGeneralItalic.ttf')

W, H = 396, 198
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
    # Times-like math and text share the same font family.
    parts = [('D', 7, 0, 'italic'),
             (' = ', 7, 0, 'normal'), ('G', 7, 0, 'italic'),
             ('gen', 6.5, 2, 'normal'), (' − ', 7, 0, 'normal'),
             ('G', 7, 0, 'italic'), ('clone', 6.5, 2, 'normal')]
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
    text(ax, x, y, f'({letter})', 8, INK)
    text(ax, x+13, y, label, 8, weight='bold')


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
    mark(ax, 10, 8)
    text(ax, 16, 3, 'Generated', 7.5, TEAL, 'bold')
    mark(ax, 116, 8, clone=True)
    text(ax, 122, 3, 'Same code', 7.5, AMBER, 'bold')
    if illustrated:
        art = mpimg.imread(HERE / 'assets/programs_and_rolls.png')
        aw = 100
        ah = aw*art.shape[0]/art.shape[1]
        # The entire original illustration remains intact. Labels are external.
        ax.imshow(art, extent=(52, 52+aw, 12+ah, 12),
                  interpolation='none', resample=False, aspect='equal', zorder=-1)
        text(ax, 8, 20, '8 programs', 7, TEAL)
        text(ax, 8, 30, '+ baseline', 7, MUTED)
        text(ax, 158, 20, '9 identical', 7, AMBER)
        text(ax, 158, 30, 'baseline slots', 7, MUTED)
    else:
        from matplotlib.transforms import Affine2D
        for i in range(9):
            for xx, clone in [(8, False), (114, True)]:
                before = set(ax.get_children())
                program(ax, 0, 0, i, clone)
                tr = Affine2D().scale(.72).translate(xx+i*9.5, 16)+ax.transData
                for artist in set(ax.get_children())-before:
                    artist.set_transform(tr)
        text(ax, 8, 34, '8 programs + baseline', 7, MUTED)
        text(ax, 114, 34, '9 identical baseline slots', 7, MUTED)
    text(ax, 8, 47, '386 common MATH-500 tasks · 3 repeats/slot', 7, MUTED)


def protocol(ax):
    text(ax, 219, 3, 'Discover → freeze → validate', 7.5, weight='bold')
    # All three held-out rotations remain visible, independent of plot heights.
    for j in range(3):
        text(ax, 226+j*15, 15, f'R{j+1}', 6.5, MUTED, ha='center')
    for i in range(3):
        for j in range(3):
            x, y = 219+j*15, 25+i*9
            held = i == j
            box(ax, x, y, 13, 8, BLUE if held else '#E4EDF3',
                BLUE if held else '#BCD0DD', 1, .4)
            if held:
                text(ax, x+6.5, y+4, 'test', 6.5, 'white',
                     ha='center', va='center')
    text(ax, 264, 50, '3 folds', 6.5, MUTED)
    arrow(ax, (266, 33), (280, 33), BLUE)
    box(ax, 286, 16, 101, 21, '#E4EDF3', '#BCD0DD')
    text(ax, 336.5, 18, '2 repeats: freeze choices', 7, ha='center', weight='bold')
    text(ax, 336.5, 27, 'per-task member + best fixed', 6.5, MUTED, ha='center')
    arrow(ax, (336.5, 37), (336.5, 42), BLUE)
    box(ax, 286, 42, 101, 13, BLUE, BLUE)
    text(ax, 336.5, 44, 'Held-out repeat: gain G', 7, 'white', ha='center')


def coverage(ax):
    heading(ax, 8, 65, 'a', 'Coverage')
    text(ax, 8, 77, 'Oracle · execution-matched', 7, MUTED)
    x0, x1, y0, y1 = 29, 125, 99, 141
    px = lambda v: x0+(v-3)/24*(x1-x0)
    py = lambda v: y1-(v-98.2)/.6*(y1-y0)
    for v in (98.2, 98.4, 98.6, 98.8):
        line(ax, x0, py(v), x1, py(v), GRID, .45)
        text(ax, x0-4, py(v), f'{v:.1f}', 6.5, MUTED, ha='right', va='center')
    line(ax, x0, y0, x0, y1, MUTED, .45)
    line(ax, x0, y1, x1, y1, MUTED, .45)
    for v in (3, 9, 18, 27):
        line(ax, px(v), y1, px(v), y1+2, MUTED, .4)
        text(ax, px(v), y1+4, str(v), 6.5, MUTED, ha='center')
    xs = [px(r['executions']) for r in D['replay']]
    for key, clone in [('clone_oracle', True), ('panel_oracle', False)]:
        ys = [py(r[key]*100) for r in D['replay']]
        ax.plot(xs, ys, color=AMBER if clone else TEAL, lw=1.0,
                ls=(0, (2, 1.5)) if clone else '-',
                marker='s' if clone else 'o', markersize=2.6,
                markerfacecolor='white' if clone else TEAL,
                markeredgewidth=.6, zorder=4 if clone else 3)
    text(ax, 8, 90, '%', 6.5, MUTED)
    text(ax, 78, 90, 'At 27: 98.70% both', 7.5, weight='bold', ha='center')
    text(ax, 77, 155, 'Harness executions', 7, MUTED, ha='center')
    line(ax, 8, 166, 128, 166, RULE, .45)
    text(ax, 8, 169, 'Repeat-mean oracle headroom · pp', 6.8, MUTED)
    for yy, key, clone in [(182, 'eval_real', False), (192, 'eval_clone', True)]:
        v = D['repeat_plugin'][key]['headroom_pp']
        c = AMBER if clone else TEAL
        mark(ax, 12, yy, clone)
        ax.add_patch(Rectangle((22, yy-2.7), v*28, 5.4,
                               facecolor=c, edgecolor='none'))
        if clone:
            ax.add_patch(Rectangle((22, yy-2.7), v*28, 5.4,
                                   facecolor='none', edgecolor='white', lw=0, hatch='////'))
        text(ax, 123, yy, f'{v:.2f}', 8, c, 'bold', 'right', 'center')
    line(ax, 22, 178, 22, 195, MUTED, .45)


def repeatability(ax):
    heading(ax, 141, 65, 'b', 'Repeatability')
    text(ax, 141, 77, 'Residual r · 95% CI', 7, MUTED)
    px = lambda v: 153 + (v+.1)/1.1*101
    for v in (0, .5, 1):
        line(ax, px(v), 92, px(v), 130, GRID, .45)
        text(ax, px(v), 132, f'{v:g}', 6.5, MUTED, ha='center')
    for key, yy, clone in [('eval_real', 102, False), ('eval_clone', 122, True)]:
        s = D['repeatability'][key]
        v = s['mean_pearson_residualized']
        lo, hi = s['mean_pearson_residualized_ci95']
        c = AMBER if clone else TEAL
        line(ax, px(lo), yy, px(hi), yy, c, 1.25)
        for q in (lo, hi):
            line(ax, px(q), yy-2.6, px(q), yy+2.6, c, .75)
        mark(ax, px(v), yy, clone, 4)
        text(ax, px(v), yy-14, f'{v:.3f}', 8, c, 'bold', 'center')
    line(ax, 141, 145, 261, 145, RULE, .45)
    text(ax, 141, 148, 'Persistent scores vs baseline', 7, MUTED)
    text(ax, 141, 159, 'Any member · 3/3 repeats · tasks', 6.8, MUTED)
    # A unit square represents one task. Counts are never rounded or rescaled.
    nloss = D['repeatability']['eval_real']['all_repeat_patterns']['loss_tasks']
    nwin = D['repeatability']['eval_real']['all_repeat_patterns']['win_tasks']
    for i in range(nloss):
        x, y = 142 + (i % 20)*3, 171+(i//20)*3
        ax.add_patch(Rectangle((x, y), 2.1, 2.1, facecolor=LOSS, edgecolor='none'))
    text(ax, 207, 170, f'{nloss}', 9, LOSS, 'bold')
    text(ax, 224, 172, 'losses', 7, MUTED)
    ax.add_patch(Rectangle((142, 190), 2.1, 2.1, facecolor=TEAL, edgecolor='none'))
    text(ax, 147, 187, f'{nwin} win*', 7, TEAL, 'bold')
    text(ax, 175, 187, '*Extraction-sensitive', 6.5, MUTED)


def lock(ax, x, y, color=BLUE):
    box(ax, x, y+4, 7, 6, '#E4EDF3', color, 1, .5)
    ax.add_patch(matplotlib.patches.Arc((x+3.5, y+4), 4, 6,
                                       theta1=0, theta2=180, color=color, lw=.6))
    ax.add_patch(Circle((x+3.5, y+7), .6, facecolor=color, edgecolor='none'))


def selection(ax):
    heading(ax, 274, 65, 'c', 'Useful selection')
    text(ax, 274, 77, 'Clone-adjusted held-out gain · pp', 6.8, MUTED)
    px = lambda v: 281 + (v+2)/4*98
    line(ax, px(0), 92, px(0), 122, '#93A2AE', .6, ls=(0, (2, 2)))
    line(ax, px(-2), 119, px(2), 119, MUTED, .45)
    for v in (-2, -1, 0, 1, 2):
        line(ax, px(v), 119, px(v), 121, MUTED, .4)
        text(ax, px(v), 123, str(v).replace('-', '−'), 6.5, MUTED, ha='center')
    s = D['primary']['paired_difference']
    lo, hi = [v*100 for v in s['D_ci95']]
    v = s['D_real_minus_clone']*100
    line(ax, px(lo), 103, px(hi), 103, BLUE, 1.3)
    for q in (lo, hi):
        line(ax, px(q), 100, px(q), 106, BLUE, .75)
    ax.plot(px(v), 103, marker='D', color=BLUE, markersize=4.1,
            markeredgecolor='white', markeredgewidth=.45, zorder=6)
    text(ax, px(v), 89, f'{v:+.2f}'.replace('-', '−'), 8.5, BLUE, 'bold', 'center')
    text(ax, 331, 135, '95% CI [−1.45, +0.95]', 7, MUTED, ha='center')
    text(ax, 331, 148, 'Complementarity unresolved', 7.5, weight='bold', ha='center')
    line(ax, 274, 162, 388, 162, RULE, .45)
    lock(ax, 275, 165)
    text(ax, 286, 165, 'Frozen feature selector', 7.5, weight='bold')
    arrow(ax, (280, 184), (290, 184), BLUE)
    text(ax, 294, 178, 'Baseline', 7, BLUE, 'bold')
    text(ax, 294, 188, '386/386 tasks', 6.8, MUTED)
    text(ax, 388, 177, '0.00 pp', 8, weight='bold', ha='right')
    text(ax, 388, 188, 'gain', 6.8, MUTED, ha='right')


def draw(illustrated=False):
    fig, ax = canvas()
    study(ax, illustrated)
    protocol(ax)
    line(ax, 209, 4, 209, 54, RULE, .55)
    line(ax, 8, 60, 388, 60, '#BECBD4', .65)
    coverage(ax)
    repeatability(ax)
    selection(ax)
    line(ax, 134, 67, 134, 194, RULE, .45)
    line(ax, 267, 67, 267, 194, RULE, .45)
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
        'version': 'v4', 'source': str(SOURCE.relative_to(ROOT)),
        'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'base_commit': '922c914cc7ce218e43b5a7114e582cf35632d253',
        'data_transformations': ['Source proportions × 100 for percent and pp.',
                                 'Display rounding only. All nine replay budgets shown.',
                                 'One persistent-loss square per task; no invented data.'],
        'schematics': 'Program motifs and repeat-fold cells are conceptual protocol diagrams.',
        'fonts': 'STIX General Regular and Bold; Times-like serif; embedded TrueType.',
        'layout': {'aspect_ratio': W/H, 'width_in': W/72, 'height_in': H/72,
                   'height_reduction_from_v3_percent': (1-H/269)*100,
                   'fraction_of_manuscript_text_height': H/648},
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
