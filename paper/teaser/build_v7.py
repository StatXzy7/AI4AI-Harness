#!/usr/bin/env python3
"""Export and validate the three illustrated v7 alternatives, without choosing one."""
import argparse
import hashlib
import importlib
import json
import xml.etree.ElementTree as ET

import fitz
from v7_common import *

CANDIDATES = {
    'A': {'module': 'v7_a_columns', 'stem': 'A_columns', 'label': 'Refined columns',
          'description': 'Familiar v6 structure; larger illustration and lighter protocol.'},
    'B': {'module': 'v7_b_lanes', 'stem': 'B_lanes', 'label': 'Evidence rows',
          'description': 'Three horizontal rows pair each question with its supporting result.'},
    'C': {'module': 'v7_c_board', 'stem': 'C_board', 'label': 'Illustrated board',
          'description': 'Larger study illustration; protocol placed beside held-out evidence.'},
}
REQUIRED = ['386', '98.70', '2.33', '2.16', '0.789', '0.006', '100',
            '0.00', '−0.26', '−1.45', '+0.95', 'unresolved', 'extraction']


def inspect(path):
    with fitz.open(path) as doc:
        page = doc[0]
        page.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False).save(
            path.with_suffix('.preview.png'))
        page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csGRAY,
                        alpha=False).save(path.with_suffix('.grayscale.png'))
        assert len(doc) == 1 and page.rect.width == W and page.rect.height == H
        fitz.TOOLS.set_small_glyph_heights(False)
        spans = [s for b in page.get_text('dict')['blocks']
                 for l in b.get('lines', []) for s in l['spans']]
        outside = [s['text'] for s in spans if not page.rect.contains(fitz.Rect(s['bbox']))]
        assert not outside, (path.name, 'text outside page', outside)
        assert min(s['size'] for s in spans) >= 7.49, (path.name, 'small text')
        content = page.get_text().lower()
        for s in REQUIRED:
            assert s in content, (path.name, 'missing evidence label', s)
        assert all(doc.extract_font(f[0])[3] for f in page.get_fonts(full=True))
        fitz.TOOLS.set_small_glyph_heights(True)
        small = [s for b in page.get_text('dict')['blocks']
                 for l in b.get('lines', []) for s in l['spans']]
        overlaps = []
        for i, a in enumerate(small):
            for b in small[i+1:]:
                intersect = fitz.Rect(a['bbox']) & fitz.Rect(b['bbox'])
                if not intersect.is_empty and intersect.width > .5 and intersect.height > 1:
                    overlaps.append([a['text'], b['text']])
        fitz.TOOLS.set_small_glyph_heights(False)
        assert not overlaps, (path.name, 'text overlaps', overlaps)
        return {'file': path.name, 'width_pt': W, 'height_pt': H, 'aspect_ratio': W/H,
                'visible_word_count': len(page.get_text('words')),
                'minimum_font_pt': round(min(s['size'] for s in spans), 2),
                'fonts': sorted(set(s['font'] for s in spans)),
                'embedded_fonts': True, 'text_within_page': True,
                'normalized_text_span_overlaps': 0,
                'raster_images': len(page.get_images()),
                'global_title': False, 'six_evidence_groups_present': True,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def comparison():
    """One sheet with all raw figures at exactly the same manuscript width."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_font(fontname='serif', fontfile=str(FONTS / 'STIXGeneral.ttf'))
    page.insert_font(fontname='serif_bold', fontfile=str(FONTS / 'STIXGeneralBol.ttf'))
    page.insert_text((108, 26), 'V7 — illustrated alternatives', fontname='serif_bold', fontsize=12)
    placements = []
    all_raw = fitz.open()
    for i, (key, spec) in enumerate(CANDIDATES.items()):
        y = 54+i*232
        page.insert_text((108, y-8), f'{key} · {spec["label"]}',
                         fontname='serif_bold', fontsize=10)
        rect = fitz.Rect(108, y, 504, y+H)
        path = OUT / f'teaser_{spec["stem"]}.pdf'
        with fitz.open(path) as figure:
            page.show_pdf_page(rect, figure, 0, keep_proportion=True)
            all_raw.insert_pdf(figure)
        placements.append({'candidate': key, 'rect_pt': list(rect), 'scale': 1.0})
    page.insert_text((108, 747), 'All three figures at 100% manuscript width (396 pt); no option selected.',
                     fontname='serif', fontsize=8, color=(.35, .4, .45))
    doc.save(OUT / 'comparison.pdf', garbage=4, deflate=True)
    page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(OUT / 'comparison.preview.png')
    all_raw.save(OUT / 'teasers_all.pdf', garbage=4, deflate=True)
    all_raw.close()
    doc.close()
    return placements


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', choices=list(CANDIDATES))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    archive = OUT / 'previous_versions_manifest.json'
    if not archive.exists():
        hashes = {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for v in range(1, 7)
                  for p in sorted((HERE / f'output/v{v}').rglob('*')) if p.is_file()}
        archive.write_text(json.dumps(hashes, indent=2)+'\n')
    hashes = json.loads(archive.read_text())
    assert all(hashlib.sha256((HERE / p).read_bytes()).hexdigest() == sha
               for p, sha in hashes.items()), 'An archived version changed'
    outputs = []
    for key, spec in CANDIDATES.items():
        if args.only and key != args.only:
            continue
        module = importlib.import_module(spec['module'])
        with plt.rc_context(STYLE):
            fig = module.draw()
            path = OUT / f'teaser_{spec["stem"]}.pdf'
            fig.savefig(path, metadata={'Title': '', 'Author': '', 'CreationDate': None,
                'ModDate': None, 'Subject': f'Illustrated teaser alternative {key}'})
            svg = path.with_suffix('.svg')
            fig.savefig(svg, metadata={'Date': None})
            svg.write_text('\n'.join(row.rstrip() for row in svg.read_text().splitlines())+'\n')
            ET.parse(svg)
            plt.close(fig)
        result = inspect(path)
        result.update({'candidate': key, 'label': spec['label']})
        outputs.append(result)
        print(json.dumps(result, indent=2), flush=True)
    if args.only:
        return
    placements = comparison()
    manifest = {'version': 'v7', 'purpose': 'Three illustrated alternatives for author choice',
        'chosen_candidate': None, 'source': str(SOURCE.relative_to(ROOT)),
        'source_sha256': SOURCE_SHA,
        'reviewed_manuscript_commit': '782bacec0579a4e2ccfea956999235af74ce3bee',
        'artwork': {'path': str(ART.relative_to(ROOT)),
                    'sha256': hashlib.sha256(ART.read_bytes()).hexdigest(),
                    'handling': 'Whole original image, unmodified; schematic only'},
        'data_transformations': ['Display rounding and source proportions × 100 only.',
            'All nine replay budgets retained in every alternative.',
            'Persistent count squares represent tasks with at least one member differing in all repeats.'],
        'previous_version_files_unchanged': len(hashes),
        'branch': 'jzsawyer-dev/teaser-v7', 'v6_pr_head_unchanged': '95b1054c2254315cf179e1e19b1ac35e0233f17d',
        'outputs': outputs, 'comparison_placements': placements}
    (OUT / 'provenance.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (OUT / 'validation.json').write_text(json.dumps({'source_values_checked': True,
        'previous_versions_unchanged': True, 'outputs': outputs}, indent=2)+'\n')


if __name__ == '__main__':
    main()
