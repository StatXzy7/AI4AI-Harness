#!/usr/bin/env python3
"""Render two standalone teaser PDFs from the paper's frozen analysis.

No manuscript files are modified. Text and measurements remain vector content;
only the explicitly illustrative variant embeds an AI-generated bitmap.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import FancyBboxPatch, Circle, Rectangle
from matplotlib.backends.backend_pdf import PdfPages
import fitz

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'artifacts/common386_20260926/analysis.json'
DATA = json.loads(SOURCE.read_text())
OUT = HERE / 'output'
OUT.mkdir(exist_ok=True)

INK = '#183042'
MUTED = '#536371'
TEAL = '#087F83'
AMBER = '#A66A19'
PALE_TEAL = '#EDF7F6'
PALE_AMBER = '#FCF5E8'
LINE = '#D3DDE2'
CORAL = '#AA4D55'
W = 396.0  # 5.5 inches, matching the repository's ICLR text width.

plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'font.size': 7,
    'pdf.fonttype': 42,
    'ps.fonttype': 42,
    'svg.fonttype': 'none',
    'axes.unicode_minus': True,
    'savefig.facecolor': 'white',
})


def text(ax, x, y, value, size=7, color=INK, weight='normal', align='left', **kw):
    return ax.text(x, y, value, fontsize=size, color=color, weight=weight,
                   ha=align, va='top', linespacing=1.3, **kw)


def line(ax, x1, y1, x2, y2, color=LINE, width=.6, **kw):
    return ax.plot([x1, x2], [y1, y2], color=color, lw=width,
                   solid_capstyle='round', **kw)


def box(ax, x, y, width, height, fill, edge='none', radius=3, lw=.6):
    patch = FancyBboxPatch((x, y), width, height,
                          boxstyle=f'round,pad=0,rounding_size={radius}',
                          facecolor=fill, edgecolor=edge, linewidth=lw)
    ax.add_patch(patch)
    return patch


def dot(ax, x, y, radius=1.15, color=TEAL, fill=None):
    ax.add_patch(Circle((x, y), radius, facecolor=fill or color,
                        edgecolor=color, lw=.55))


def program(ax, x, y, color, kind, width=15, height=24):
    """Schematic glyphs; their topology is illustrative, not an empirical trace."""
    box(ax, x, y, width, height, 'white', color, radius=1.8, lw=.65)
    line(ax, x+3, y+4, x+7, y+4, color, .7)
    if kind == 0:
        pts = [(7.5, 9), (7.5, 14), (7.5, 19)]
        edges = [(0, 1), (1, 2)]
    elif kind % 4 == 1:
        pts = [(7.5, 8), (4, 14), (11, 14), (7.5, 20)]
        edges = [(0, 1), (0, 2), (1, 3), (2, 3)]
    elif kind % 4 == 2:
        pts = [(4, 8), (4, 14), (11, 14), (11, 20)]
        edges = [(0, 1), (1, 2), (2, 3)]
    elif kind % 4 == 3:
        pts = [(7.5, 8), (4, 14), (11, 14), (4, 20)]
        edges = [(0, 1), (0, 2), (1, 3)]
    else:
        pts = [(4, 9), (11, 9), (11, 18), (4, 18)]
        edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    for i, j in edges:
        line(ax, x+pts[i][0], y+pts[i][1], x+pts[j][0], y+pts[j][1], color, .65)
    for px, py in pts:
        dot(ax, x+px, y+py, .9, color)


def heading(ax, x, y, letter, title):
    dot(ax, x+4, y+4.5, 5, INK)
    ax.text(x+4, y+4.4, letter, fontsize=6.5, color='white',
            ha='center', va='center', weight='bold')
    text(ax, x+13, y-.2, title, 8.3, weight='bold')


def figure(style):
    illustrated = style == 'illustrated'
    shift = 99 if illustrated else 0
    height = 324 + shift
    fig = plt.figure(figsize=(W/72, height/72), facecolor='white')
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, W), ylim=(height, 0))
    ax.set_axis_off()

    text(ax, 7, 4, 'More programs, or more rolls?', 14.0, weight='bold')
    text(ax, 7, 26, f"{DATA['n_tasks']} MATH-500 tasks · 9 slots per arm · 3 repeats per slot", 7.25, MUTED)
    text(ax, 97, 48, 'Generated panel', 8.4, TEAL, 'bold', 'center')
    text(ax, 300, 48, 'Same-code control', 8.4, AMBER, 'bold', 'center')

    if illustrated:
        art = mpimg.imread(HERE / 'assets/programs_and_rolls.png')
        art_h = 384 * art.shape[0] / art.shape[1]
        ax.imshow(art, extent=(6, 390, 59+art_h, 59), aspect='equal',
                  interpolation='none', resample=False, zorder=-1)
    else:
        box(ax, 7, 61, 183, 34, PALE_TEAL, radius=4)
        box(ax, 207, 61, 183, 34, PALE_AMBER, radius=4)
        shades = [TEAL, '#38768E', '#7769A8', TEAL, '#38768E', '#7769A8', TEAL, '#38768E', INK]
        for i in range(9):
            program(ax, 13+i*19.6, 66, shades[i], i+1 if i < 8 else 0)
            program(ax, 213+i*19.6, 66, AMBER, 0)
        text(ax, 198, 73, 'vs', 6.9, MUTED, align='center')

    text(ax, 98, 99+shift, '8 generated programs + baseline', 6.9, MUTED, align='center')
    text(ax, 298, 99+shift, '9 byte-identical baseline slots', 6.9, MUTED, align='center')
    line(ax, 7, 113+shift, 389, 113+shift)

    # Three evidence questions. All plotted values are read from analysis.json.
    y = 123 + shift
    heading(ax, 8, y, 'a', 'Coverage')
    heading(ax, 141, y, 'b', 'Repeatability')
    heading(ax, 274, y, 'c', 'Usable selection')
    line(ax, 132, y+1, 132, y+133, width=.45)
    line(ax, 265, y+1, 265, y+133, width=.45)

    # Panel a: bar lengths share a true zero and identical scale.
    text(ax, 8, y+18, 'Repeat-mean oracle headroom', 6.55, MUTED)
    scale = 80 / 2.6
    for label, key, color, offset in [
        ('Generated', 'eval_real', TEAL, 38),
        ('Same code', 'eval_clone', AMBER, 72),
    ]:
        val = DATA['repeat_plugin'][key]['headroom_pp']
        yy = y+offset
        text(ax, 8, yy, label, 7.1, color, weight='bold')
        box(ax, 8, yy+13, 80, 8, '#F0F3F5', radius=0)
        box(ax, 8, yy+13, val*scale, 8, color, radius=0)
        if key == 'eval_clone':
            ax.add_patch(Rectangle((8, yy+13), val*scale, 8,
                                  facecolor='none', edgecolor='white',
                                  hatch='////', linewidth=0))
        text(ax, 124, yy+11.5, f'{val:.2f}', 8.2, INK, 'bold', 'right')
    text(ax, 8, y+99, '0', 6.1, MUTED)
    text(ax, 88, y+99, '2.6 pp', 6.1, MUTED, align='right')
    text(ax, 8, y+116, 'Identical code still produces\npositive oracle headroom.', 6.9, weight='bold')

    # Panel b: observed residual correlations and the source's bootstrap CIs.
    text(ax, 141, y+18, 'Residual score correlation', 6.65, MUTED)
    bx, bw = 145, 111
    sx = lambda val: bx + (val+.12)/1.14*bw
    for label, key, color, marker, offset in [
        ('Generated', 'eval_real', TEAL, 'o', 38),
        ('Same code', 'eval_clone', AMBER, 's', 72),
    ]:
        stats = DATA['repeatability'][key]
        value = stats['mean_pearson_residualized']
        lo, hi = stats['mean_pearson_residualized_ci95']
        yy = y+offset
        text(ax, 141, yy, label, 7.1, color, weight='bold')
        text(ax, 256, yy, f'{value:.3f}', 8.1, INK, 'bold', 'right')
        line(ax, sx(-.1), yy+18, sx(1), yy+18, '#E6ECEF', .55)
        line(ax, sx(lo), yy+18, sx(hi), yy+18, color, 1.35)
        for end in (lo, hi):
            line(ax, sx(end), yy+15.5, sx(end), yy+20.5, color, .8)
        ax.plot(sx(value), yy+18, marker=marker, ms=3.8, color=color,
                markeredgecolor='white', markeredgewidth=.5)
    for val in (0, .5, 1):
        text(ax, sx(val), y+99, f'{val:g}', 6.1, MUTED, align='center')
    patterns = DATA['repeatability']['eval_real']['all_repeat_patterns']
    text(ax, 141, y+113, 'All 3 repeats vs baseline:', 6.6, MUTED)
    text(ax, 141, y+126,
         f"{patterns['loss_tasks']} loss tasks · {patterns['win_tasks']} win task*",
         6.9, weight='bold')

    # Panel c: distinguish actual pre-execution selection from oracle replay.
    text(ax, 274, y+18, 'Frozen selector gain', 7.0, MUTED)
    gain = DATA['selector']['gain_vs_bare_pp']
    text(ax, 274, y+36, f'{gain:.2f}', 24.5, weight='bold')
    text(ax, 343, y+51, 'pp', 9.5, MUTED)
    text(ax, 274, y+68, 'vs development-fixed baseline', 6.35, MUTED)
    line(ax, 274, y+83, 388, y+83)
    text(ax, 274, y+92, '27-execution oracle coverage', 6.45, MUTED)
    coverage = DATA['replay'][-1]['panel_oracle']*100
    text(ax, 274, y+106, f'{coverage:.2f}%', 17.0, weight='bold')
    text(ax, 274, y+129, 'Equal in both arms', 6.9, MUTED)

    # Visible boundary: no unsupported claim of equivalence or deployable gain.
    foot = y+149
    box(ax, 7, foot, 382, 26, '#F0F4F6', radius=3)
    p = DATA['primary']['paired_difference']
    d = p['D_real_minus_clone']*100
    lo, hi = [v*100 for v in p['D_ci95']]
    signed = lambda value: f'{value:+.2f}'.replace('-', '−')
    detail = f'Clone-adjusted held-out gain: {signed(d)} pp   ·   95% CI [{signed(lo)}, {signed(hi)}]'
    text(ax, 14, foot+4, detail, 6.9, MUTED)
    text(ax, 14, foot+14.5, 'Stable complementarity remains unresolved.', 7.4, weight='bold')
    text(ax, 8, foot+32, 'Error bars: 95% bootstrap CIs. *The single win is sensitive to answer extraction.', 6.0, MUTED)
    text(ax, 8, foot+41, 'Matched harness executions; model-call and token costs vary. Program icons are schematic.', 6.0, MUTED)
    return fig


def metadata(style):
    return {
        'Title': f'More Programs or More Rolls? — {style.capitalize()} teaser',
        'Author': '',
        'Subject': 'Same-code control, coverage, repeatability, and usable selection on 386 MATH-500 tasks',
        'Keywords': 'AI4AI-Harness, teaser, MATH-500, same-code control',
        'Creator': 'Matplotlib; exact values from common386_20260926/analysis.json',
    }


def inspect(path):
    doc = fitz.open(path)
    page = doc[0]
    fonts = page.get_fonts(full=True)
    report = {
        'file': path.name,
        'pages': len(doc),
        'width_pt': round(page.rect.width, 3),
        'height_pt': round(page.rect.height, 3),
        'images': len(page.get_images()),
        'image_details': [
            {'width_px': item['width'], 'height_px': item['height'],
             'effective_ppi_x': round(item['width'] * 72 / (item['bbox'][2]-item['bbox'][0]), 1)}
            for item in page.get_image_info()
        ],
        'fonts': [{'type': f[2], 'name': f[3]} for f in fonts],
        'text_characters': len(page.get_text()),
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    # Inspection previews are separate from the paper-ready PDF deliverable.
    page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False).save(
        str(path.with_suffix('.preview.png')))
    doc.close()
    return report


def main():
    reports = []
    with PdfPages(OUT / 'teaser_both_styles.pdf', metadata=metadata('two design options')) as both:
        for style in ['academic', 'illustrated']:
            fig = figure(style)
            path = OUT / f'teaser_{style}.pdf'
            fig.savefig(path, metadata=metadata(style), dpi=600)
            fig.savefig(OUT / f'teaser_{style}.svg', dpi=600)
            both.savefig(fig, dpi=600)
            plt.close(fig)
            reports.append(inspect(path))
    manifest = {
        'source': str(SOURCE.relative_to(ROOT)),
        'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'base_commit': '922c914cc7ce218e43b5a7114e582cf35632d253',
        'values_recomputed': False,
        'transformations': ['Proportions multiplied by 100 where labeled percent or pp.',
                            'Display rounding: 2 decimals for pp/percent; 3 for correlations.'],
        'ci': '95% bootstrap intervals already stored in the frozen analysis; not recomputed.',
        'art': 'AI-generated conceptual illustration; does not represent measured traces or outcomes.',
        'matplotlib': matplotlib.__version__,
        'outputs': reports,
    }
    (OUT / 'provenance.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
