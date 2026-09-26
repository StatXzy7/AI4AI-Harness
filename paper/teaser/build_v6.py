#!/usr/bin/env python3
"""Information-rich illustrated teaser; writes only output/v6/."""
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'artifacts/common386_20260926/analysis.json'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == (
    '253a2587fa67d3be8e830a22582497ec7c26ba6ee67db10ef85b5735cfa2ca21'
), 'This version is tied to the reviewed 26 September 2026 evidence snapshot.'
D = json.loads(SOURCE.read_text())
OUT = HERE / 'output/v6'
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
    'font.family': REG.get_name(), 'font.size': 7.5,
    'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none',
    'svg.hashsalt': 'ai4ai-teaser-v6',
    'axes.unicode_minus': True, 'savefig.facecolor': 'white',
    'mathtext.fontset': 'stix',
})


def text(ax, x, y, s, size=7.5, color=INK, weight='normal', ha='left', va='top', **kw):
    fp = SEMI if weight == 'bold' else ITAL if weight == 'italic' else REG
    return ax.text(x, y, s, fontsize=size, fontproperties=fp, color=color,
                   ha=ha, va=va, linespacing=1.07, **kw)


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
    text(ax, x+13, y, label, 8.5, weight='bold')


def canvas():
    fig = plt.figure(figsize=(W/72, H/72), facecolor='white')
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, W), ylim=(H, 0))
    ax.set_axis_off()
    return fig, ax


def study(ax):
    # The shared scope replaces repeated panel-level setup text.
    text(ax, 8, 3, f'{D["n_tasks"]} complete MATH-500 tasks · 3 repeats/slot', 7.5, MUTED)
    art = mpimg.imread(HERE / 'assets/programs_and_rolls.png')
    aw = 124
    ah = aw*art.shape[0]/art.shape[1]
    # Keep the whole artwork intact, enlarging its width by 24% versus v4.
    ax.imshow(art, extent=(41, 41+aw, 14+ah, 14),
              interpolation='none', resample=False, aspect='equal', zorder=-1)
    mark(ax, 9, 27)
    text(ax, 15, 21, '8 generated', 7.5, TEAL, 'bold')
    text(ax, 15, 32, '+ baseline', 7.5, MUTED)
    mark(ax, 166, 27, clone=True)
    text(ax, 172, 21, '9 identical', 7.5, AMBER, 'bold')
    text(ax, 172, 32, 'baseline slots', 7.5, MUTED)


def protocol(ax):
    text(ax, 221, 4, '3-fold: discover → freeze → test', 8, weight='bold')
    # All three held-out rotations remain visible, independent of plot heights.
    for j in range(3):
        text(ax, 227+j*15, 17, f'R{j+1}', 7.5, MUTED, ha='center')
    for i in range(3):
        for j in range(3):
            x, y = 220+j*15, 29+i*9
            held = i == j
            box(ax, x, y, 13, 8, BLUE if held else '#E4EDF3',
                BLUE if held else '#BCD0DD', 1, .4)
            if held:
                text(ax, x+6.5, y+4, 'test', 7.5, 'white',
                     ha='center', va='center')
    arrow(ax, (266, 36), (276, 36), BLUE)
    box(ax, 280, 18, 108, 22, '#E4EDF3', '#BCD0DD')
    text(ax, 334, 20, '2 repeats: freeze choices', 7.5, ha='center', weight='bold')
    text(ax, 334, 30, 'per-task + best fixed member', 7.5, MUTED, ha='center')
    arrow(ax, (334, 40), (334, 45), BLUE)
    box(ax, 280, 45, 108, 12, BLUE, BLUE)
    text(ax, 334, 46.5, 'Held-out repeat: gain G', 7.5, 'white', ha='center')


def coverage(ax):
    heading(ax, 8, 65, 'a', 'Coverage')
    text(ax, 8, 78, 'Oracle · execution-matched', 7.5, MUTED)
    x0, x1, y0, y1 = 30, 126, 106, 141
    px = lambda v: x0+(v-3)/24*(x1-x0)
    py = lambda v: y1-(v-98.2)/.6*(y1-y0)
    for v in (98.2, 98.4, 98.6, 98.8):
        line(ax, x0, py(v), x1, py(v), GRID, .45)
        text(ax, x0-4, py(v), f'{v:.1f}', 7.5, MUTED, ha='right', va='center')
    line(ax, x0, y0, x0, y1, MUTED, .45)
    line(ax, x0, y1, x1, y1, MUTED, .45)
    for v in (3, 9, 18, 27):
        line(ax, px(v), y1, px(v), y1+2, MUTED, .4)
        text(ax, px(v), y1+4, str(v), 7.5, MUTED, ha='center')
    xs = [px(r['executions']) for r in D['replay']]
    for key, clone in [('clone_oracle', True), ('panel_oracle', False)]:
        ys = [py(r[key]*100) for r in D['replay']]
        ax.plot(xs, ys, color=AMBER if clone else TEAL, lw=1.0,
                ls=(0, (2, 1.5)) if clone else '-',
                marker='s' if clone else 'o', markersize=2.6,
                markerfacecolor='white' if clone else TEAL,
                markeredgewidth=.6, zorder=4 if clone else 3)
    text(ax, 8, 93, '%', 7.5, MUTED)
    final = D['replay'][-1]
    assert final['panel_oracle'] == final['clone_oracle']
    text(ax, 81, 92, f'At {final["executions"]}: {100*final["panel_oracle"]:.2f}% both',
         8, weight='bold', ha='center')
    text(ax, 78, 155, 'Harness executions', 7.5, MUTED, ha='center')
    text(ax, 8, 168, 'Repeat-mean headroom (pp)', 7.5, MUTED)
    for yy, key, clone in [(182, 'eval_real', False), (191, 'eval_clone', True)]:
        v = D['repeat_plugin'][key]['headroom_pp']
        c = AMBER if clone else TEAL
        mark(ax, 12, yy, clone)
        ax.add_patch(Rectangle((22, yy-2.7), v*28, 5.4,
                               facecolor=c, edgecolor='none'))
        if clone:
            ax.add_patch(Rectangle((22, yy-2.7), v*28, 5.4,
                                   facecolor='none', edgecolor='white', lw=0, hatch='////'))
        text(ax, 128, yy, f'{v:.2f}', 8.5, c, 'bold', 'right', 'center')
    line(ax, 22, 179, 22, 196, MUTED, .45)


def repeatability(ax):
    heading(ax, 141, 65, 'b', 'Repeatability')
    text(ax, 141, 78, 'Residual r · 95% CI', 7.5, MUTED)
    px = lambda v: 153 + (v+.1)/1.1*101
    for v in (0, .5, 1):
        line(ax, px(v), 92, px(v), 130, GRID, .45)
        text(ax, px(v), 132, f'{v:g}', 7.5, MUTED, ha='center')
    for key, yy, clone in [('eval_real', 102, False), ('eval_clone', 122, True)]:
        s = D['repeatability'][key]
        v = s['mean_pearson_residualized']
        lo, hi = s['mean_pearson_residualized_ci95']
        c = AMBER if clone else TEAL
        line(ax, px(lo), yy, px(hi), yy, c, 1.25)
        for q in (lo, hi):
            line(ax, px(q), yy-2.6, px(q), yy+2.6, c, .75)
        mark(ax, px(v), yy, clone, 4)
        text(ax, px(v), yy-14, f'{v:.3f}', 9, c, 'bold', 'center')
    line(ax, 141, 145, 261, 145, RULE, .45)
    text(ax, 141, 148, 'Persistent scores vs baseline', 7.5, MUTED)
    text(ax, 141, 159, 'Tasks · any member · 3/3 repeats', 7.5, MUTED)
    # A unit square represents one task. Counts are never rounded or rescaled.
    nloss = D['repeatability']['eval_real']['all_repeat_patterns']['loss_tasks']
    nwin = D['repeatability']['eval_real']['all_repeat_patterns']['win_tasks']
    for i in range(nloss):
        x, y = 142 + (i % 20)*3, 171+(i//20)*3
        ax.add_patch(Rectangle((x, y), 2.1, 2.1, facecolor=LOSS, edgecolor='none'))
    text(ax, 207, 170, f'{nloss}', 9, LOSS, 'bold')
    text(ax, 224, 172, 'losses', 7.5, MUTED)
    ax.add_patch(Rectangle((142, 190), 2.1, 2.1, facecolor=TEAL, edgecolor='none'))
    text(ax, 147, 187, f'{nwin} win*', 7.5, TEAL, 'bold')
    text(ax, 177, 187, '*Extraction-sensitive', 7.5, MUTED)


def lock(ax, x, y, color=BLUE):
    box(ax, x, y+4, 7, 6, '#E4EDF3', color, 1, .5)
    ax.add_patch(matplotlib.patches.Arc((x+3.5, y+4), 4, 6,
                                       theta1=0, theta2=180, color=color, lw=.6))
    ax.add_patch(Circle((x+3.5, y+7), .6, facecolor=color, edgecolor='none'))


def selection(ax):
    heading(ax, 274, 65, 'c', 'Useful selection')
    text(ax, 274, 78, 'Clone-adjusted held-out gain (pp)', 7.5, MUTED)
    px = lambda v: 281 + (v+2)/4*98
    line(ax, px(0), 92, px(0), 122, '#93A2AE', .6, ls=(0, (2, 2)))
    line(ax, px(-2), 119, px(2), 119, MUTED, .45)
    for v in (-2, -1, 0, 1, 2):
        line(ax, px(v), 119, px(v), 121, MUTED, .4)
        text(ax, px(v), 123, str(v).replace('-', '−'), 7.5, MUTED, ha='center')
    s = D['primary']['paired_difference']
    lo, hi = [v*100 for v in s['D_ci95']]
    v = s['D_real_minus_clone']*100
    line(ax, px(lo), 103, px(hi), 103, BLUE, 1.3)
    for q in (lo, hi):
        line(ax, px(q), 100, px(q), 106, BLUE, .75)
    ax.plot(px(v), 103, marker='D', color=BLUE, markersize=4.1,
            markeredgecolor='white', markeredgewidth=.45, zorder=6)
    text(ax, px(v), 89, f'{v:+.2f}'.replace('-', '−'), 10, BLUE, 'bold', 'center')
    text(ax, 331, 137, f'95% CI [{lo:+.2f}, {hi:+.2f}]'.replace('-', '−'),
         7.5, MUTED, ha='center')
    text(ax, 331, 150, 'Specialization unresolved', 8, weight='bold', ha='center')
    line(ax, 274, 162, 388, 162, RULE, .45)
    lock(ax, 275, 165)
    text(ax, 286, 165, 'Frozen feature selector', 8, weight='bold')
    arrow(ax, (276, 187), (283, 187), BLUE)
    text(ax, 286, 181, 'Baseline', 7.5, BLUE, 'bold')
    policy = D['selector']
    text(ax, 318, 181, f'({policy["choices_on_subset"]["bare"]}/{D["n_tasks"]})', 7.5, MUTED)
    text(ax, 388, 180, f'{policy["gain_vs_bare_pp"]:.2f} pp', 9, weight='bold', ha='right')
    text(ax, 388, 165, 'gain', 7.5, MUTED, ha='right')


def draw():
    fig, ax = canvas()
    study(ax)
    protocol(ax)
    arrow(ax, (203, 51), (216, 51), MUTED, .65, 5)
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
        assert min(s['size'] for s in spans) >= 7.49
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
    archive = OUT / 'previous_versions_manifest.json'
    if not archive.exists():
        prior = {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for version in ('v1', 'v2', 'v3', 'v4', 'v5')
                 for p in sorted((HERE / 'output' / version).rglob('*')) if p.is_file()}
        archive.write_text(json.dumps(prior, indent=2)+'\n')
    prior = json.loads(archive.read_text())
    assert all(hashlib.sha256((HERE / p).read_bytes()).hexdigest() == h
               for p, h in prior.items()), 'A previous version changed'
    fig = draw()
    path = OUT / 'teaser_illustrated.pdf'
    fig.savefig(path, metadata={'Title': '', 'Author': '',
                               'Subject': 'Coverage, repeatable scored patterns, and useful selection',
                               'CreationDate': None, 'ModDate': None})
    svg = path.with_suffix('.svg')
    fig.savefig(svg, metadata={'Date': None})
    svg.write_text('\n'.join(row.rstrip() for row in svg.read_text().splitlines())+'\n')
    plt.close(fig)
    outputs = [inspect(path)]
    manifest = {
        'version': 'v6', 'variant': 'illustrated only', 'source': str(SOURCE.relative_to(ROOT)),
        'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'source_base_commit': '922c914cc7ce218e43b5a7114e582cf35632d253',
        'reviewed_manuscript_commit': '782bacec0579a4e2ccfea956999235af74ce3bee',
        'data_transformations': ['Source proportions × 100 for percent and pp.',
                                 'Display rounding only. All nine replay budgets shown.',
                                 'One persistent-loss square per task; no invented data.'],
        'schematics': 'Program motifs and repeat-fold cells are conceptual protocol diagrams.',
        'fonts': 'STIX General Regular and Bold; Times-like serif; embedded TrueType.',
        'layout': {'aspect_ratio': W/H, 'width_in': W/72, 'height_in': H/72,
                   'fraction_of_manuscript_text_height': H/648,
                   'artwork_width_pt': 124, 'minimum_text_pt': 7.5},
        'artwork': 'Unmodified whole original bitmap; all data and text are vector.',
        'restored_from_v4': ['All nine oracle-coverage budgets and 98.70% endpoint tie.',
                            'Residual correlations and 95% intervals for both arms.',
                            'Frozen feature selector: baseline on 386/386 tasks, 0.00 pp gain.'],
        'retained_from_v5': ['Same-code control and repeat-mean headroom 2.33/2.16 pp.',
                            'Persistent losses: 100 tasks; win: 1 task, extraction-sensitive.',
                            'Clone-adjusted held-out gain −0.26 pp and CI; specialization unresolved.'],
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
