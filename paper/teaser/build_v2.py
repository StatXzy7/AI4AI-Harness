#!/usr/bin/env python3
"""Concise, title-free teaser alternatives. Writes only output/v2/."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle
import fitz

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'artifacts/common386_20260926/analysis.json'
DATA = json.loads(SOURCE.read_text())
OUT = HERE / 'output' / 'v2'
OUT.mkdir(parents=True, exist_ok=True)
W = 396
INK, MUTED = '#183042', '#566775'
TEAL, AMBER = '#087F83', '#A66A19'
RULE = '#D7E0E4'

plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'pdf.fonttype': 42,
    'ps.fonttype': 42,
    'svg.fonttype': 'none',
    'axes.unicode_minus': True,
    'savefig.facecolor': 'white',
})


def text(ax, x, y, s, size=7, color=INK, weight='normal', ha='left'):
    return ax.text(x, y, s, fontsize=size, color=color, weight=weight,
                   ha=ha, va='top', linespacing=1.2)


def line(ax, x1, y1, x2, y2, color=RULE, lw=.55):
    ax.plot([x1, x2], [y1, y2], color=color, lw=lw,
            solid_capstyle='round', clip_on=False)


def marker(ax, x, y, clone=False, size=3.8):
    ax.plot(x, y, marker='s' if clone else 'o', ms=size,
            color=AMBER if clone else TEAL,
            markeredgecolor='white', markeredgewidth=.4)


def canvas(height):
    fig = plt.figure(figsize=(W/72, height/72), facecolor='white')
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, W), ylim=(height, 0))
    ax.set_axis_off()
    return fig, ax


def card(ax, x, y, k, clone=False):
    color = AMBER if clone else TEAL if k < 8 else INK
    ax.add_patch(FancyBboxPatch((x, y), 8.1, 17.5,
                               boxstyle='round,pad=0,rounding_size=1',
                               facecolor='white', edgecolor=color, lw=.5))
    if clone or k == 8:
        pts = [(4, 4), (4, 9), (4, 14)]
        edges = [(0, 1), (1, 2)]
    else:
        motifs = [
            ([(4, 4), (2, 9), (6, 9), (4, 14)], [(0, 1), (0, 2), (1, 3), (2, 3)]),
            ([(2, 4), (2, 9), (6, 9), (6, 14)], [(0, 1), (1, 2), (2, 3)]),
            ([(4, 4), (2, 9), (6, 9), (2, 14)], [(0, 1), (0, 2), (1, 3)]),
            ([(2, 4), (6, 4), (6, 14), (2, 14)], [(0, 1), (1, 2), (2, 3), (3, 0)]),
            ([(2, 4), (6, 9), (2, 14)], [(0, 1), (1, 2), (2, 0)]),
            ([(4, 4), (2, 14), (6, 14)], [(0, 1), (0, 2)]),
            ([(2, 4), (6, 4), (4, 9), (4, 14)], [(0, 2), (1, 2), (2, 3)]),
            ([(2, 4), (2, 9), (6, 9), (6, 14)], [(0, 1), (1, 2), (2, 3), (3, 1)]),
        ]
        pts, edges = motifs[k]
    for a, b in edges:
        line(ax, x+pts[a][0], y+pts[a][1], x+pts[b][0], y+pts[b][1], color, .45)
    for px, py in pts:
        ax.add_patch(Circle((x+px, y+py), .65, facecolor=color, edgecolor='none'))


def academic():
    """Control first: three empirical questions and the unresolved boundary."""
    fig, ax = canvas(186)
    marker(ax, 10, 10)
    text(ax, 16, 5, 'Generated', 7.5, TEAL, 'bold')
    text(ax, 8, 20, '8 programs + baseline', 6.4, MUTED)
    marker(ax, 210, 10, clone=True)
    text(ax, 216, 5, 'Same code', 7.5, AMBER, 'bold')
    text(ax, 208, 20, '9 identical slots', 6.4, MUTED)
    for i in range(9):
        card(ax, 103+i*9.7, 7, i)
        card(ax, 303+i*9.7, 7, i, clone=True)
    line(ax, 8, 37, 389, 37)
    text(ax, 198, 43, f"{DATA['n_tasks']} MATH-500 tasks · 3 repeats/slot", 6.8, MUTED, ha='center')

    text(ax, 8, 65, 'Oracle headroom', 8.25, weight='bold')
    text(ax, 8, 79, 'Repeat-averaged · pp', 6.45, MUTED)
    text(ax, 141, 65, 'Repeatability', 8.25, weight='bold')
    text(ax, 141, 79, 'Residual r · 95% CI', 6.45, MUTED)
    text(ax, 274, 65, 'Frozen selector', 8.25, weight='bold')
    line(ax, 132, 66, 132, 143, lw=.45)
    line(ax, 265, 66, 265, 143, lw=.45)

    # Shared zero; directly labeled quantities. Circle/square and hatch encoding
    # carry the arm distinction when the page is viewed without color.
    for key, yy, clone in [('eval_real', 101, False), ('eval_clone', 124, True)]:
        color = AMBER if clone else TEAL
        value = DATA['repeat_plugin'][key]['headroom_pp']
        marker(ax, 10, yy, clone)
        ax.add_patch(Rectangle((20, yy-3.5), value*24, 7,
                               facecolor=color, edgecolor=color, lw=0))
        if clone:
            ax.add_patch(Rectangle((20, yy-3.5), value*24, 7,
                                   facecolor='none', edgecolor='white',
                                   hatch='////', lw=0))
        text(ax, 124, yy-5.3, f'{value:.2f}', 9.0, weight='bold', ha='right')
    line(ax, 20, 95, 20, 129, MUTED, .45)
    line(ax, 20, 132, 92, 132, RULE, .5)
    for tick in [0, 1, 2, 3]:
        line(ax, 20+tick*24, 131, 20+tick*24, 133, MUTED, .4)
        text(ax, 20+tick*24, 135, str(tick), 5.9, MUTED, ha='center')

    px = lambda v: 157 + (v+.1)/1.1*96
    for key, yy, clone in [('eval_real', 101, False), ('eval_clone', 124, True)]:
        s = DATA['repeatability'][key]
        val = s['mean_pearson_residualized']
        low, high = s['mean_pearson_residualized_ci95']
        color = AMBER if clone else TEAL
        line(ax, px(-.1), yy, px(1), yy, '#E7ECEF', .5)
        line(ax, px(low), yy, px(high), yy, color, 1.1)
        for v in (low, high):
            line(ax, px(v), yy-2.5, px(v), yy+2.5, color, .7)
        marker(ax, px(val), yy, clone, 4)
        text(ax, 256, yy-13.2, f'{val:.3f}', 7.9, color, 'bold', 'right')
    for val in (0, .5, 1):
        text(ax, px(val), 135, f'{val:g}', 5.9, MUTED, ha='center')

    gain = DATA['selector']['gain_vs_bare_pp']
    text(ax, 274, 94, f'{gain:.2f}', 23, weight='bold')
    text(ax, 339, 107, 'pp', 8.0, MUTED)
    text(ax, 274, 130, 'gain vs fixed baseline', 6.4, MUTED)

    line(ax, 8, 151, 389, 151)
    p = DATA['primary']['paired_difference']
    signed = lambda v: f'{v*100:+.2f}'.replace('-', '−')
    lo, hi = p['D_ci95']
    detail = (f"Clone-adjusted held-out gain: {signed(p['D_real_minus_clone'])} pp "
              f"[{signed(lo)}, {signed(hi)}] · 95% CI")
    text(ax, 198, 157, detail, 6.4, MUTED, ha='center')
    text(ax, 198, 170, 'Stable complementarity unresolved', 7.8, weight='bold', ha='center')
    return fig


def illustrated():
    """Result first: the comparison scene feeds a visually dominant oracle tie."""
    fig, ax = canvas(178)
    text(ax, 198, 4, f"{DATA['n_tasks']} MATH-500 tasks · 9 slots/arm × 3 repeats", 6.8, MUTED, ha='center')
    line(ax, 8, 19, 389, 19)
    text(ax, 48, 28, 'Generated', 7.1, TEAL, 'bold', 'center')
    text(ax, 126, 28, 'Same code', 7.1, AMBER, 'bold', 'center')
    marker(ax, 24, 32, size=3.3)
    marker(ax, 102, 32, clone=True, size=3.3)
    art = mpimg.imread(HERE / 'assets/programs_and_rolls.png')
    art_w = 174
    art_h = art_w*art.shape[0]/art.shape[1]
    ax.imshow(art, extent=(0, art_w, 42+art_h, 42),
              interpolation='none', resample=False, aspect='equal', zorder=-1)
    text(ax, 48, 104, '8 + baseline', 6.3, MUTED, ha='center')
    text(ax, 126, 104, '9 clones', 6.3, MUTED, ha='center')
    text(ax, 87, 120, 'Repeat-mean oracle headroom (pp)', 6.6, MUTED, ha='center')
    for key, xx, color in [('eval_real', 48, TEAL), ('eval_clone', 126, AMBER)]:
        text(ax, xx, 133, f"{DATA['repeat_plugin'][key]['headroom_pp']:.2f}",
             11.4, color, 'bold', 'center')

    line(ax, 175, 28, 175, 145, lw=.45)
    line(ax, 294, 28, 294, 145, lw=.45)
    text(ax, 235, 29, 'Oracle coverage', 8.25, weight='bold', ha='center')
    text(ax, 235, 44, '27 executions', 6.6, MUTED, ha='center')
    coverage = DATA['replay'][-1]['panel_oracle']*100
    text(ax, 235, 75, f'{coverage:.2f}%', 20, weight='bold', ha='center')
    marker(ax, 213, 111)
    marker(ax, 256, 111, clone=True)
    line(ax, 218, 111, 227, 111, TEAL, .85)
    line(ax, 242, 111, 251, 111, AMBER, .85)
    text(ax, 235, 103, '=', 12, MUTED, ha='center')
    text(ax, 235, 124, 'Both arms', 7.2, MUTED, ha='center')

    text(ax, 304, 29, 'Repeatability', 8, weight='bold')
    text(ax, 304, 44, 'Residual r', 6.45, MUTED)
    real_r = DATA['repeatability']['eval_real']['mean_pearson_residualized']
    clone_r = DATA['repeatability']['eval_clone']['mean_pearson_residualized']
    marker(ax, 302, 63, size=2.8)
    marker(ax, 351, 63, clone=True, size=2.8)
    text(ax, 308, 58, f'{real_r:.3f}', 9.8, TEAL, 'bold')
    text(ax, 343, 59, '/', 8.0, MUTED)
    text(ax, 357, 58, f'{clone_r:.3f}', 9.8, AMBER, 'bold')
    line(ax, 304, 83, 388, 83)
    text(ax, 304, 93, 'Frozen selector', 7.8, weight='bold')
    text(ax, 304, 108, f"{DATA['selector']['gain_vs_bare_pp']:.2f}", 19.3, weight='bold')
    text(ax, 361, 119, 'pp', 7.5, MUTED)
    text(ax, 304, 134, 'gain vs baseline', 6.45, MUTED)
    line(ax, 8, 154, 389, 154)
    text(ax, 198, 162, 'Stable complementarity unresolved', 7.8, weight='bold', ha='center')
    return fig


def inspect(path):
    with fitz.open(path) as doc:
        page = doc[0]
        spans = [s for b in page.get_text('dict')['blocks']
                 for l in b.get('lines', []) for s in l['spans']]
        outside = [s['text'] for s in spans if not page.rect.contains(fitz.Rect(s['bbox']))]
        assert not outside, outside
        embedded = all(doc.extract_font(f[0])[3] for f in page.get_fonts(full=True))
        assert embedded
        txt = page.get_text()
        assert 'More programs' not in txt
        for required in ['386', '2.33', '2.16', '0.789', '0.006', '0.00', 'unresolved']:
            assert required in txt, required
        page.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False).save(str(path.with_suffix('.preview.png')))
        page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csGRAY, alpha=False).save(
            str(path.with_suffix('.grayscale.png')))
        return {
            'file': path.name,
            'page_count': len(doc),
            'width_pt': page.rect.width,
            'height_pt': page.rect.height,
            'visible_word_count': len(page.get_text('words')),
            'raster_images': len(page.get_images()),
            'embedded_fonts': bool(embedded),
            'text_within_page': not outside,
            'global_title': False,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        }


def main():
    outputs = []
    metadata = {'Title': 'AI4AI-Harness teaser — v2', 'Author': '',
                'Subject': 'Title-free concise teaser alternatives',
                'Creator': 'Matplotlib; frozen common386_20260926 analysis'}
    with PdfPages(OUT/'teaser_both_styles.pdf', metadata=metadata) as both:
        for style, build in [('academic', academic), ('illustrated', illustrated)]:
            fig = build()
            path = OUT/f'teaser_{style}.pdf'
            fig.savefig(path, metadata=metadata, dpi=600)
            fig.savefig(path.with_suffix('.svg'), dpi=600)
            both.savefig(fig, dpi=600)
            plt.close(fig)
            outputs.append(inspect(path))
    (OUT/'provenance.json').write_text(json.dumps({
        'version': 'v2',
        'source': str(SOURCE.relative_to(ROOT)),
        'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'base_commit': '922c914cc7ce218e43b5a7114e582cf35632d253',
        'data_transformations': ['Percent / pp = source proportion × 100.',
                                 'Display rounding only; no data or uncertainty recomputation.'],
        'artwork': 'Unmodified v1 conceptual artwork reused only in illustrated PDF.',
        'design_intent': 'No global title; concise labels; control-first and result-first alternatives.',
        'matplotlib': matplotlib.__version__,
        'outputs': outputs,
    }, indent=2)+'\n')
    print(json.dumps(outputs, indent=2))


if __name__ == '__main__':
    main()
