#!/usr/bin/env python3
"""Compose honest page-fit proofs without modifying or compiling the manuscript."""
from pathlib import Path
import hashlib
import json
import fitz

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'output/v4'
FONT = HERE / 'assets/fonts/STIXGeneral.ttf'
ORIGINAL = ROOT / 'paper/latex/main.pdf'
CAPTION = (
    'Figure 1: Coverage, repeatability, and useful selection. The same 386 tasks '
    'are used throughout. Headroom is repeat-averaged; oracle replay matches '
    'harness executions, not tokens or model calls. Persistent scored '
    'differences require any generated member to win/lose against baseline '
    'in all three repeats; the sole win is extraction-sensitive. Error bars '
    'show 95% bootstrap intervals. Program glyphs are schematic.'
)


def proof(source, figure, mode):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # The original running header and surrounding text are placed as vector PDF
    # excerpts, not fabricated typography or a claim of successful compilation.
    header = fitz.Rect(0, 0, 612, 60)
    page.show_pdf_page(header, source, 1, clip=header)
    rect = fitz.Rect(108, 82, 504, 280)
    page.show_pdf_page(rect, figure, 0, keep_proportion=True)
    page.insert_font(fontname='caption_serif', fontfile=str(FONT))
    cap = fitz.Rect(108, 289, 504, 377)
    rem = page.insert_textbox(cap, CAPTION, fontsize=10, lineheight=1.12,
                              fontname='caption_serif', align=fitz.TEXT_ALIGN_JUSTIFY)
    assert rem >= 0, 'Caption does not fit at 10 pt'
    cap_spans = [s for b in page.get_text('dict')['blocks']
                 for l in b.get('lines', []) for s in l['spans']
                 if s['font'] == 'STIXGeneral-Regular']
    caption_bottom = max(s['bbox'][3] for s in cap_spans)
    # One intact excerpt begins at a full paragraph and ends at the end of a
    # related-work paragraph. Its original line breaking and fonts are retained.
    crop = fitz.Rect(108, 323, 504, 598)
    body_top = caption_bottom + 18
    dest = fitz.Rect(108, body_top, 504, body_top + crop.height)
    assert dest.y1 < 732
    page.show_pdf_page(dest, source, 1, clip=crop, keep_proportion=True)
    page.insert_text((108, 757),
        f'{mode.capitalize()} layout proof | figure at 100% | original text excerpt | not a LaTeX compile',
        fontsize=8, fontname='caption_serif', color=(.35, .4, .45))
    target = OUT / f'paper_fit_{mode}.pdf'
    doc.save(target, garbage=4, deflate=True)
    page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(
        target.with_suffix('.preview.png'))
    data = {
        'mode': mode, 'figure_rect_pt': list(rect),
        'figure_scale': 1.0, 'figure_aspect_ratio': 2.0,
        'caption_size_pt': 10, 'caption_height_pt': caption_bottom-cap.y0,
        'figure_caption_spacing_pt': cap.y0-rect.y1,
        'caption_body_spacing_pt': 18,
        'total_figure_caption_and_spacing_pt': body_top-rect.y0,
        'body_excerpt_bottom_pt': dest.y1,
        'method': 'PDF composition with original text excerpt, not reflow or LaTeX compilation',
    }
    return doc, data


def main():
    before = hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()
    reports = []
    with fitz.open(ORIGINAL) as source, fitz.open() as both:
        for mode in ['academic', 'illustrated']:
            with fitz.open(OUT / f'teaser_{mode}.pdf') as figure:
                doc, report = proof(source, figure, mode)
                both.insert_pdf(doc)
                doc.close()
                reports.append(report)
        both.save(OUT / 'paper_fit_both_styles.pdf', garbage=4, deflate=True)
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == before
    (OUT / 'paper_fit_validation.json').write_text(json.dumps({
        'original_manuscript_pdf_sha256': before, 'original_pdf_unchanged': True,
        'manuscript_text_width_pt': 396, 'manuscript_text_height_pt': 648,
        'reports': reports}, indent=2)+'\n')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
