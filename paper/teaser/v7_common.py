"""Shared immutable evidence, typography, and drawing primitives for v7."""
from pathlib import Path
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, Rectangle, FancyBboxPatch, FancyArrowPatch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'output/v7'
SOURCE = ROOT / 'artifacts/common386_20260926/analysis.json'
SOURCE_SHA = '253a2587fa67d3be8e830a22582497ec7c26ba6ee67db10ef85b5735cfa2ca21'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SOURCE_SHA
D = json.loads(SOURCE.read_text())
ART = HERE / 'assets/programs_and_rolls.png'
FONTS = HERE / 'assets/fonts'
for font in FONTS.glob('STIXGeneral*.ttf'):
    font_manager.fontManager.addfont(str(font))
REG = FontProperties(fname=FONTS / 'STIXGeneral.ttf')
BOLD = FontProperties(fname=FONTS / 'STIXGeneralBol.ttf')
ITAL = FontProperties(fname=FONTS / 'STIXGeneralItalic.ttf')
W, H = 396, 198
INK, MUTED, RULE, GRID = '#24333F', '#596775', '#D6DDE2', '#E8EDF0'
TEAL, AMBER, BLUE, LOSS = '#087C83', '#A76815', '#3D587A', '#AF625E'
TPALE, APALE, BPALE = '#EEF7F6', '#FCF5EA', '#E8EFF5'
STYLE = {'font.family': REG.get_name(), 'font.size': 7.5,
         'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none',
         'svg.hashsalt': 'ai4ai-teaser-v7', 'axes.unicode_minus': True,
         'savefig.facecolor': 'white', 'mathtext.fontset': 'stix'}


def text(ax, x, y, s, size=7.5, color=INK, bold=False,
         ha='left', va='top', italic=False, **kwargs):
    return ax.text(x, y, s, fontsize=size,
                   fontproperties=BOLD if bold else ITAL if italic else REG,
                   color=color, ha=ha, va=va, linespacing=1.08, **kwargs)


def line(ax, x1, y1, x2, y2, color=RULE, lw=.55, **kwargs):
    return ax.plot([x1, x2], [y1, y2], color=color, lw=lw,
                   solid_capstyle='round', clip_on=False, **kwargs)


def box(ax, x, y, w, h, fill='white', edge=RULE, radius=2, lw=.55):
    artist = FancyBboxPatch((x, y), w, h,
        boxstyle=f'round,pad=0,rounding_size={radius}',
        facecolor=fill, edgecolor=edge, linewidth=lw)
    ax.add_patch(artist)
    return artist


def arrow(ax, a, b, color=MUTED, lw=.7, scale=5):
    artist = FancyArrowPatch(a, b, arrowstyle='-|>', mutation_scale=scale,
        color=color, linewidth=lw, shrinkA=0, shrinkB=0)
    ax.add_patch(artist)
    return artist


def mark(ax, x, y, clone=False, size=3.5, color=None):
    return ax.plot(x, y, marker='s' if clone else 'o', markersize=size,
        color=color or (AMBER if clone else TEAL), markeredgecolor='white',
        markeredgewidth=.35, zorder=7)


def panel_label(ax, x, y, letter, label):
    text(ax, x, y, f'({letter})', 8)
    text(ax, x+13, y, label, 8.5, bold=True)


def art(ax, x, y, width):
    """Place the entire, unmodified original bitmap; no image editing."""
    pixels = mpimg.imread(ART)
    height = width*pixels.shape[0]/pixels.shape[1]
    ax.imshow(pixels, extent=(x, x+width, y+height, y),
              interpolation='none', resample=False, aspect='equal', zorder=-1)
    return height


def canvas():
    fig = plt.figure(figsize=(W/72, H/72), facecolor='white')
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, W), ylim=(H, 0))
    ax.set_axis_off()
    return fig, ax
