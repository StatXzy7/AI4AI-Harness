#!/usr/bin/env python3
"""Natural-size PDF placement proofs, without changing or compiling LaTeX."""
import hashlib
import json
from pathlib import Path

import fitz

HERE = Path(__file__).resolve().parent
OUT = HERE / 'output/v8'
ORIGINAL = HERE.parents[1] / 'paper/latex/main.pdf'
FONT = HERE / 'assets/fonts/STIXGeneral.ttf'
EXPECTED = 'aca6a579b56203ec299e494c3af7d9d4f9f853d20510882612596ab494271e00'
COMMON = (
    'Coverage, repeatable scores, and useful selection on 386 complete MATH tasks. '
    'Both arms freeze per-task choices and a best fixed member on two repeats, '
    'then measure gain G on the held-out repeat. D subtracts the same-code gain. '
    'Oracle budgets count harness executions. Intervals are 95% bootstrap CIs; '
    'the sole persistent win is extraction-sensitive. '
)
CAPTIONS = {
    'A_calibrated': 'Figure 1: ' + COMMON +
        'Persistent task counts require at least one generated member to differ from baseline in all three repeats.',
    'B_fingerprint': 'Figure 1: ' + COMMON +
        'Example #138 is deliberately selected to illustrate the recorded outcomes; it is not representative.',
    'C_crossover': 'Figure 1: ' + COMMON +
        'The top-right sketches are population success-probability examples, not observed task curves. '
        'Stable complementarity requires the better member to change across tasks.',
}


def main():
    before = hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()
    assert before == EXPECTED, 'Review the page proof if the manuscript snapshot changes.'
    reports = []
    with fitz.open(ORIGINAL) as source, fitz.open() as result:
        for key, caption in CAPTIONS.items():
            figure_path = OUT / f'teaser_{key}.pdf'
            page = result.new_page(width=612, height=792)
            header = fitz.Rect(0, 0, 612, 60)
            page.show_pdf_page(header, source, 1, clip=header)
            page.insert_font(fontname='serif', fontfile=str(FONT))
            page.insert_text((108, 73), 'V8 · ' + key.replace('_', ' — '),
                             fontname='serif', fontsize=9, color=(.35, .4, .45))
            rect = fitz.Rect(108, 82, 504, 280)
            with fitz.open(figure_path) as figure:
                assert len(figure) == 1 and tuple(figure[0].rect) == (0, 0, 396, 198)
                page.show_pdf_page(rect, figure, 0)
            caprect = fitz.Rect(108, 289, 504, 390)
            remainder = page.insert_textbox(caprect, caption, fontname='serif', fontsize=10,
                                           lineheight=1.12, align=fitz.TEXT_ALIGN_JUSTIFY)
            assert remainder >= 0
            spans = [s for b in page.get_text('dict')['blocks'] for l in b.get('lines', [])
                     for s in l['spans'] if s['bbox'][1] >= caprect.y0-1]
            bottom = max(s['bbox'][3] for s in spans)
            # End below a complete paragraph, rather than clipping a text line.
            crop = fitz.Rect(108, 323, 504, 598)
            dest = fitz.Rect(108, bottom+18, 504, bottom+18+crop.height)
            assert dest.y1 < 732
            page.show_pdf_page(dest, source, 1, clip=crop)
            page.insert_text((108, 757),
                '100% size · local manuscript 922c914 · PDF composition, not a LaTeX compile',
                fontname='serif', fontsize=8, color=(.35, .4, .45))
            page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(
                OUT / f'paper_fit_{key}.preview.png')
            reports.append({'figure': figure_path.name, 'page': len(result), 'scale': 1.0,
                            'raw_figure_sha256': hashlib.sha256(figure_path.read_bytes()).hexdigest(),
                            'figure_rect_pt': list(rect), 'caption': caption,
                            'caption_words': len(caption.split()), 'caption_size_pt': 10,
                            'caption_height_pt': bottom-caprect.y0,
                            'body_excerpt_bottom_pt': dest.y1})
        result.save(OUT / 'paper_fit_all.pdf', garbage=4, deflate=True)
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == before
    validation = {'original_pdf_sha256': before, 'original_pdf_unchanged': True,
                  'method': 'PDF composition, not a LaTeX compilation or pagination check.',
                  'manuscript_snapshot': '922c914', 'reports': reports}
    (OUT / 'paper_fit_validation.json').write_text(json.dumps(validation, indent=2)+'\n')
    print(json.dumps(validation, indent=2))


if __name__ == '__main__':
    main()
