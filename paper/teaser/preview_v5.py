#!/usr/bin/env python3
"""Make one illustrated page-fit proof; never modify or compile the manuscript."""
from pathlib import Path
import hashlib
import json

import fitz


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'output/v5'
FONT = HERE / 'assets/fonts/STIXGeneral.ttf'
ORIGINAL = ROOT / 'paper/latex/main.pdf'
FIGURE = OUT / 'teaser_illustrated.pdf'
MANUSCRIPT_SNAPSHOT = '922c914cc7ce218e43b5a7114e582cf35632d253'
EXPECTED_MANUSCRIPT_SHA256 = (
    'aca6a579b56203ec299e494c3af7d9d4f9f853d20510882612596ab494271e00'
)
CAPTION = (
    'Figure 1: Controlled diagnosis of program specialization. Both arms use '
    '386 complete MATH tasks, nine slots, and three repeats. Headroom uses '
    'repeat means. Persistent tasks have at least one generated member '
    'winning/losing against baseline in all three repeats; the sole win is '
    'extraction-sensitive. D is clone-adjusted held-out repeat gain '
    '(95% bootstrap CI). Program drawings are schematic.'
)


def proof(source, figure):
    """Place the raw PDF at natural size beside original manuscript excerpts."""
    assert len(figure) == 1, 'Expected one raw teaser page'
    size = figure[0].rect
    assert abs(size.width - 396) < .01 and abs(size.height - 198) < .01, (
        'The page proof expects a 396 x 198 pt teaser; update its layout '
        'explicitly if the figure dimensions change.'
    )
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Preserve original vector running header and text. These excerpts are a
    # visual composition, not evidence of reflow or successful LaTeX compilation.
    header = fitz.Rect(0, 0, 612, 60)
    page.show_pdf_page(header, source, 1, clip=header)
    rect = fitz.Rect(108, 82, 504, 280)
    page.show_pdf_page(rect, figure, 0, keep_proportion=True)
    page.insert_font(fontname='caption_serif', fontfile=str(FONT))
    cap = fitz.Rect(108, 289, 504, 377)
    remaining = page.insert_textbox(
        cap, CAPTION, fontsize=10, lineheight=1.12,
        fontname='caption_serif', align=fitz.TEXT_ALIGN_JUSTIFY,
    )
    assert remaining >= 0, 'Caption does not fit at 10 pt'
    cap_spans = [
        span for block in page.get_text('dict')['blocks']
        for line in block.get('lines', []) for span in line['spans']
        if span['font'] == 'STIXGeneral-Regular'
        and span['bbox'][1] >= cap.y0 - 1
    ]
    assert cap_spans, 'Expected extractable caption text'
    caption_bottom = max(span['bbox'][3] for span in cap_spans)
    crop = fitz.Rect(108, 323, 504, 598)
    body_top = caption_bottom + 18
    dest = fitz.Rect(108, body_top, 504, body_top + crop.height)
    assert dest.y1 < 732, 'Body excerpt extends beyond the text area'
    page.show_pdf_page(dest, source, 1, clip=crop, keep_proportion=True)
    page.insert_text(
        (108, 757),
        'Layout proof at 100% | local manuscript 922c914 | not a LaTeX compile',
        fontsize=8, fontname='caption_serif', color=(.35, .4, .45),
    )
    target = OUT / 'paper_fit_illustrated.pdf'
    doc.save(target, garbage=4, deflate=True)
    page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(
        target.with_suffix('.preview.png')
    )
    report = {
        'mode': 'illustrated',
        'figure_rect_pt': list(rect),
        'figure_scale': 1.0,
        'figure_aspect_ratio': 2.0,
        'caption': CAPTION,
        'caption_word_count': len(CAPTION.split()),
        'caption_size_pt': 10,
        'caption_height_pt': caption_bottom - cap.y0,
        'figure_caption_spacing_pt': cap.y0 - rect.y1,
        'caption_body_spacing_pt': 18,
        'total_figure_caption_and_spacing_pt': body_top - rect.y0,
        'body_excerpt_bottom_pt': dest.y1,
        'method': 'PDF composition with original text excerpt; no reflow or LaTeX compilation',
    }
    doc.close()
    return report


def main():
    before = hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()
    assert before == EXPECTED_MANUSCRIPT_SHA256, (
        'The local manuscript PDF changed; review excerpt geometry and '
        'snapshot provenance before making this proof.'
    )
    with fitz.open(ORIGINAL) as source, fitz.open(FIGURE) as figure:
        report = proof(source, figure)
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == before
    validation = {
        'original_manuscript_pdf': 'paper/latex/main.pdf',
        'original_manuscript_snapshot_commit': MANUSCRIPT_SNAPSHOT,
        'original_manuscript_pdf_sha256': before,
        'original_pdf_unchanged': True,
        'proof_uses_latest_main_manuscript': False,
        'raw_figure_sha256': hashlib.sha256(FIGURE.read_bytes()).hexdigest(),
        'manuscript_text_width_pt': 396,
        'manuscript_text_height_pt': 648,
        'reports': [report],
    }
    (OUT / 'paper_fit_validation.json').write_text(
        json.dumps(validation, indent=2) + '\n'
    )
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
