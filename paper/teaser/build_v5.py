#!/usr/bin/env python3
"""Build the illustrated v5 teaser only; preserve manuscript and v1–v4."""
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
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'output/v5'
SOURCE = ROOT / 'artifacts/common386_20260926/analysis.json'
SOURCE_SHA = '253a2587fa67d3be8e830a22582497ec7c26ba6ee67db10ef85b5735cfa2ca21'
MANUSCRIPT_COMMIT = '782bacec0579a4e2ccfea956999235af74ce3bee'
ART = HERE / 'assets/programs_and_rolls.png'
FONTS = HERE / 'assets/fonts'
W, H = 396, 198
INK, MUTED, RULE = '#25333D', '#52616D', '#D9E0E4'
TEAL, AMBER, BLUE, LOSS = '#087C83', '#9C6013', '#3D587A', '#A65855'
PALE, GRID = '#E7EFF4', '#E8EDF0'

assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SOURCE_SHA
D = json.loads(SOURCE.read_text())
for font in FONTS.glob('STIXGeneral*.ttf'):
    font_manager.fontManager.addfont(str(font))
REG = FontProperties(fname=FONTS / 'STIXGeneral.ttf')
BOLD = FontProperties(fname=FONTS / 'STIXGeneralBol.ttf')
STYLE = {'font.family': REG.get_name(), 'font.size': 7.5,
         'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none',
         'svg.hashsalt': 'ai4ai-teaser-v5',
         'axes.unicode_minus': True, 'savefig.facecolor': 'white',
         'mathtext.fontset': 'stix'}


def text(ax, x, y, label, size=7.5, color=INK, bold=False,
         ha='left', va='top'):
    return ax.text(x, y, label, fontsize=size,
                   fontproperties=BOLD if bold else REG, color=color,
                   ha=ha, va=va, linespacing=1.08)


def line(ax, x1, y1, x2, y2, color=RULE, width=.55, **kw):
    ax.plot([x1, x2], [y1, y2], color=color, lw=width,
            solid_capstyle='round', **kw)


def rounded(ax, x, y, w, h, color='white', edge=RULE, radius=2):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
        boxstyle=f'round,pad=0,rounding_size={radius}',
        facecolor=color, edgecolor=edge, linewidth=.55))


def arrow(ax, a, b, color=BLUE):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle='-|>',
        mutation_scale=5, linewidth=.6, color=color, shrinkA=0, shrinkB=0))


def heading(ax, x, letter, title):
    text(ax, x, 6, f'({letter})', 8, MUTED)
    text(ax, x+12, 6, title, 8.5, bold=True)


def control(ax):
    heading(ax, 8, 'a', 'Same-code control')
    text(ax, 47, 27, 'Generated', 8.2, TEAL, True, 'center')
    text(ax, 130, 27, 'Same code', 8.2, AMBER, True, 'center')
    for x, marker, color in [(22, 'o', TEAL), (105, 's', AMBER)]:
        ax.plot(x, 31.5, marker=marker, color=color, markersize=3,
                markeredgewidth=0)
    art = mpimg.imread(ART)
    aw = 178
    ah = aw * art.shape[0] / art.shape[1]
    # Whole original image, unmodified; artwork is explicitly schematic.
    ax.imshow(art, extent=(0, aw, 39+ah, 39), interpolation='none',
              resample=False, aspect='equal', zorder=-1)
    text(ax, 47, 101, '8 programs\n+ baseline', 7.5, MUTED, ha='center')
    text(ax, 130, 101, '9 identical\nbaseline slots', 7.5, MUTED, ha='center')

    text(ax, 8, 125, 'Repeat-mean oracle headroom', 8, bold=True)
    # Equal zero-anchored scales. pp are already supplied by the data source.
    x0, x1, max_pp = 21, 131, 3.0
    for yy, key, clone in [(146, 'eval_real', False), (163, 'eval_clone', True)]:
        v = D['repeat_plugin'][key]['headroom_pp']
        color = AMBER if clone else TEAL
        ax.plot(11, yy, marker='s' if clone else 'o', color=color,
                markersize=3.7, markeredgewidth=0)
        ax.add_patch(Rectangle((x0, yy-4), (x1-x0)*v/max_pp, 8,
                              facecolor=color, edgecolor='none'))
        if clone:
            ax.add_patch(Rectangle((x0, yy-4), (x1-x0)*v/max_pp, 8,
                facecolor='none', edgecolor='white', hatch='////', linewidth=0))
        text(ax, 174, yy, f'{v:.2f} pp', 9.5, color, True, 'right', 'center')
    line(ax, x0, 139, x0, 170, MUTED, .5)
    text(ax, x0, 171, '0', 7.5, MUTED, ha='center')


def task_mark(ax, x, y, color, w=4.8, h=2.8):
    """One task, three bars for its all-three-repeat scored difference."""
    gap = .35
    part = (w-2*gap)/3
    for i in range(3):
        ax.add_patch(Rectangle((x+i*(part+gap), y), part, h,
                              facecolor=color, edgecolor='none'))


def persistence(ax):
    heading(ax, 186, 'b', 'Repeatability')
    text(ax, 186, 27, 'Persistent scored\ndifferences', 8, bold=True)
    text(ax, 186, 50, 'Any member vs. baseline\nin all 3 repeats', 7.5, MUTED)
    nloss = D['repeatability']['eval_real']['all_repeat_patterns']['loss_tasks']
    nwin = D['repeatability']['eval_real']['all_repeat_patterns']['win_tasks']
    # One triplet glyph per task: all 100 observed persistent-loss tasks.
    for i in range(nloss):
        task_mark(ax, 188+(i % 10)*7.15, 77+(i//10)*4.25, LOSS)
    text(ax, 186, 126, f'{nloss}', 13, LOSS, True)
    text(ax, 212, 130, 'loss tasks', 8, MUTED)
    for i in range(nwin):
        task_mark(ax, 188+i*7.15, 153, TEAL)
    text(ax, 200, 149, f'{nwin} win task*', 8, TEAL, True)
    text(ax, 186, 165, '1 glyph = 1 task', 7.5, MUTED)


def held_out(ax):
    heading(ax, 282, 'c', 'Held-out gain')
    text(ax, 299, 27, 'Discover', 7.5, MUTED, ha='center')
    text(ax, 365, 27, 'Test', 7.5, BLUE, ha='center')
    for x, label, held in [(285, 'R1', False), (308, 'R2', False), (356, 'R3', True)]:
        rounded(ax, x, 39, 18, 15, BLUE if held else PALE,
                BLUE if held else '#B8CBD8')
        text(ax, x+9, 46.5, label, 7.5, 'white' if held else BLUE,
             ha='center', va='center')
    arrow(ax, (329, 46.5), (350, 46.5))
    text(ax, 335, 62, 'Freeze task-wise choice\n+ best fixed member', 7.5,
         MUTED, ha='center')
    text(ax, 335, 84, 'Rotate held-out repeat', 7.5, MUTED, ha='center')
    line(ax, 282, 97, 388, 97)
    text(ax, 335, 104, 'Clone-adjusted gain D (pp)', 7.5, MUTED, ha='center')
    s = D['primary']['paired_difference']
    v = s['D_real_minus_clone']*100
    lo, hi = [q*100 for q in s['D_ci95']]
    px = lambda q: 289 + (q+2)/4*92
    text(ax, 335, 115, f'{v:+.2f}'.replace('-', '−'), 12, BLUE, True, 'center')
    line(ax, px(0), 129, px(0), 145, '#99A7B1', .6, ls=(0, (2, 2)))
    line(ax, px(lo), 135, px(hi), 135, BLUE, 1.4)
    for q in (lo, hi):
        line(ax, px(q), 131.5, px(q), 138.5, BLUE, .75)
    ax.plot(px(v), 135, marker='D', color=BLUE, markersize=4.3,
            markeredgecolor='white', markeredgewidth=.5, zorder=4)
    line(ax, px(-2), 144, px(2), 144, MUTED, .45)
    for q in (-2, 0, 2):
        line(ax, px(q), 144, px(q), 146, MUTED, .45)
        text(ax, px(q), 147, str(q).replace('-', '−'), 7.5, MUTED, ha='center')
    ci = f'95% CI [{lo:+.2f}, {hi:+.2f}]'.replace('-', '−')
    text(ax, 335, 157, ci, 7.5, MUTED, ha='center')
    text(ax, 335, 168, 'Specialization unresolved', 8, BLUE, True, 'center')


def draw():
    fig = plt.figure(figsize=(W/72, H/72), facecolor='white')
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, W), ylim=(H, 0))
    ax.set_axis_off()
    control(ax)
    persistence(ax)
    held_out(ax)
    for x in (180, 275):
        line(ax, x, 27, x, 172, RULE, .5)
    line(ax, 8, 180, 388, 180, RULE, .55)
    text(ax, 8, 186, '386 complete MATH-500 tasks · 3 repeats/slot', 7.5, MUTED)
    text(ax, 388, 186, '*Win is extraction-sensitive.', 7.5, MUTED, ha='right')
    return fig


def inspect(path):
    with fitz.open(path) as doc:
        page = doc[0]
        spans = [s for b in page.get_text('dict')['blocks']
                 for l in b.get('lines', []) for s in l['spans']]
        assert len(doc) == 1 and page.rect.width == W and page.rect.height == H
        assert all(page.rect.contains(fitz.Rect(s['bbox'])) for s in spans)
        fonts = page.get_fonts(full=True)
        assert all(doc.extract_font(f[0])[3] for f in fonts)
        required = ['2.33', '2.16', '100', '1 win task', '−0.26', '−1.45',
                    '+0.95', '386', 'extraction-sensitive', 'best fixed', 'unresolved']
        for item in required:
            assert item in page.get_text(), item
        minimum = min(s['size'] for s in spans)
        assert minimum >= 7.49, minimum
        page.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False).save(
            path.with_suffix('.preview.png'))
        page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csGRAY,
                        alpha=False).save(path.with_suffix('.grayscale.png'))
        return {'file': path.name, 'page_count': len(doc), 'width_pt': W,
                'height_pt': H, 'aspect_ratio': W/H,
                'minimum_font_pt': round(minimum, 2),
                'visible_word_count': len(page.get_text('words')),
                'fonts': sorted(set(s['font'] for s in spans)),
                'embedded_fonts': True, 'raster_images': len(page.get_images()),
                'text_within_page': True, 'global_title': False,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    archive_path = OUT / 'previous_versions_manifest.json'
    if not archive_path.exists():
        archive = {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for version in ('v1', 'v2', 'v3', 'v4')
                   for p in sorted((HERE / 'output' / version).rglob('*')) if p.is_file()}
        archive_path.write_text(json.dumps(archive, indent=2)+'\n')
    archive = json.loads(archive_path.read_text())
    assert all(hashlib.sha256((HERE / p).read_bytes()).hexdigest() == sha
               for p, sha in archive.items()), 'A previous version changed'
    with plt.rc_context(STYLE):
        fig = draw()
        path = OUT / 'teaser_illustrated.pdf'
        fig.savefig(path, metadata={'Title': '', 'Author': '',
            'Subject': 'Same-code controls, persistent scored differences, held-out gain',
            'CreationDate': None, 'ModDate': None})
        svg = path.with_suffix('.svg')
        fig.savefig(svg, metadata={'Date': None})
        # Matplotlib emits trailing spaces in multiline SVG paths. Normalize
        # serialization for clean diffs without changing paths or artwork.
        svg.write_text('\n'.join(row.rstrip() for row in svg.read_text().splitlines())+'\n')
        plt.close(fig)
    result = inspect(path)
    manifest = {'version': 'v5', 'variant': 'illustrated only',
        'source': str(SOURCE.relative_to(ROOT)), 'source_sha256': SOURCE_SHA,
        'reviewed_manuscript_commit': MANUSCRIPT_COMMIT,
        'layout': {'width_pt': W, 'height_pt': H, 'aspect_ratio': W/H},
        'artwork': {'path': str(ART.relative_to(ROOT)),
                    'sha256': hashlib.sha256(ART.read_bytes()).hexdigest(),
                    'handling': 'Original whole image; no crop or pixel edits; schematic only'},
        'data_transformations': ['Held-out proportions × 100 to pp; display rounding only.',
            'Headroom already in pp; zero-anchored common bar scale.',
            'One triplet glyph per persistent-difference task; bars represent three repeats.'],
        'interpretation': ['Headroom bars and held-out D use different estimators.',
            'Persistent loss/win tasks: at least one generated member vs baseline in all repeats.',
            'The single win is answer-extraction sensitive.',
            'D is not stable headroom; interval crossing zero leaves specialization unresolved.',
            'Scope is the 386-task common complete set; same solver, selected low-call panel.'],
        'schematics': 'Original program motifs and R1–R3 protocol; no fabricated scored matrix.',
        'fonts': 'Bundled STIX General, regular/bold; all fonts embedded in PDF.',
        'previous_version_files_unchanged': len(archive), 'outputs': [result]}
    (OUT / 'provenance.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (OUT / 'validation.json').write_text(json.dumps({'source_values_checked': True,
        'previous_versions_unchanged': True, 'outputs': [result]}, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
