#!/usr/bin/env python3
"""Compose all three v7 figures at manuscript size without editing LaTeX."""
from pathlib import Path
import hashlib
import json

import fitz


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'output/v7'
FONT = HERE / 'assets/fonts/STIXGeneral.ttf'
ORIGINAL = ROOT / 'paper/latex/main.pdf'
MANUSCRIPT_SNAPSHOT = '922c914cc7ce218e43b5a7114e582cf35632d253'
EXPECTED_MANUSCRIPT_SHA256 = (
    'aca6a579b56203ec299e494c3af7d9d4f9f853d20510882612596ab494271e00'
)
OPTIONS = (
    ('A_columns', 'Option A: Columns'),
    ('B_lanes', 'Option B: Evidence lanes'),
    ('C_board', 'Option C: Illustrated evidence board'),
)
CAPTION = (
    'Figure 1: Coverage, repeatability, and selection on 386 complete MATH '
    'tasks. Oracle coverage matches executions, not tokens/calls; headroom '
    'uses repeat means. Persistent task counts require at least one generated '
    'member to win/lose against baseline in all three repeats; the sole win '
    'is extraction-sensitive. Intervals are 95% bootstrap CIs. Program '
    'drawings are schematic.'
)


def add_proof(doc, source, figure, option, option_label):
    """Add a natural-size figure and unmodified manuscript text excerpts."""
    assert len(figure) == 1, 'Expected one raw teaser page'
    size = figure[0].rect
    assert abs(size.width - 396) < .01 and abs(size.height - 198) < .01, (
        'The page proof expects a 396 x 198 pt teaser; update its layout '
        'explicitly if the figure dimensions change.'
    )
    assert len(CAPTION.split()) == 52, 'Keep the shared 52-word caption'
    page = doc.new_page(width=612, height=792)
    # Original vector excerpts provide typographic context, not a reflowed
    # manuscript or evidence that the latest manuscript compiles with v7.
    header = fitz.Rect(0, 0, 612, 60)
    page.show_pdf_page(header, source, 1, clip=header)
    page.insert_font(fontname='caption_serif', fontfile=str(FONT))
    page.insert_text(
        (108, 73), option_label,
        fontsize=9, fontname='caption_serif', color=(.35, .4, .45),
    )
    rect = fitz.Rect(108, 82, 504, 280)
    page.show_pdf_page(rect, figure, 0, keep_proportion=True)
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
    preview = OUT / f'paper_fit_{option}.preview.png'
    page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(preview)
    return {
        'option': option,
        'option_label': option_label,
        'proof_page': len(doc),
        'preview_file': preview.name,
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


def main():
    before = hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()
    assert before == EXPECTED_MANUSCRIPT_SHA256, (
        'The local manuscript PDF changed; review excerpt geometry and '
        'snapshot provenance before making this proof.'
    )
    figures = [(option, label, OUT / f'teaser_{option}.pdf')
               for option, label in OPTIONS]
    for _, _, figure_path in figures:
        assert figure_path.is_file(), f'Missing final figure: {figure_path}'
    reports = []
    with fitz.open(ORIGINAL) as source, fitz.open() as doc:
        for option, label, figure_path in figures:
            with fitz.open(figure_path) as figure:
                report = add_proof(doc, source, figure, option, label)
            report['raw_figure_file'] = figure_path.name
            report['raw_figure_sha256'] = hashlib.sha256(
                figure_path.read_bytes()
            ).hexdigest()
            reports.append(report)
        assert len(doc) == 3, 'Expected one page per v7 option'
        doc.save(OUT / 'paper_fit_all.pdf', garbage=4, deflate=True)
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == before
    validation = {
        'original_manuscript_pdf': 'paper/latex/main.pdf',
        'original_manuscript_snapshot_commit': MANUSCRIPT_SNAPSHOT,
        'original_manuscript_pdf_sha256': before,
        'original_pdf_unchanged': True,
        'proof_uses_latest_main_manuscript': False,
        'proof_file': 'paper_fit_all.pdf',
        'proof_pages': 3,
        'manuscript_text_width_pt': 396,
        'manuscript_text_height_pt': 648,
        'reports': reports,
    }
    (OUT / 'paper_fit_validation.json').write_text(
        json.dumps(validation, indent=2) + '\n'
    )
    print(json.dumps(validation, indent=2))


if __name__ == '__main__':
    main()
