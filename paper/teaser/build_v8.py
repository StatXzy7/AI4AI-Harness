#!/usr/bin/env python3
"""Explain the science within v6's footprint; preserve every earlier export."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import fitz
import numpy as np

import build_v6 as base
from build_v7 import inspect as inspect_pdf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'output/v8'
DATA = ROOT / 'artifacts/common386_20260926'
CANDIDATES = {
    'A': {'module': 'v8_calibrated', 'stem': 'A_calibrated',
          'label': 'Explain the control and persistent scores'},
    'B': {'module': 'v8_fingerprint', 'stem': 'B_fingerprint',
          'label': 'Illustrate the control with recorded outcomes'},
    'C': {'module': 'v8_crossover', 'stem': 'C_crossover',
          'label': 'Explain what stable specialization requires'},
}
MATRIX_HASHES = {
    'eval_real.npz': '57c98d81cb00cc2fa3cf47cfa76649be6b5f8bf556d3fa73981f93430188a9c1',
    'eval_clone.npz': 'fb76655eaa7f923e529fa484f5ecb2fb3389aff9cd7d29d49ee31ead75363feb',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_evidence():
    """Verify the newly illustrated statements against the complete raw tensors."""
    arms = {}
    for file, expected in MATRIX_HASHES.items():
        path = DATA / file
        assert sha(path) == expected, f'Unreviewed score tensor: {file}'
        with np.load(path, allow_pickle=False) as source:
            arm = {key: source[key].copy() for key in source.files}
        assert arm['stack'].shape == (3, 9, 386)
        assert np.isin(arm['stack'], [0, 1]).all()
        arms[file] = arm
    real, clone = arms['eval_real.npz'], arms['eval_clone.npz']
    assert np.array_equal(real['tasks'], clone['tasks'])
    assert real['members'][0] == 'bare'
    baseline = real['stack'][:, :1, :]
    generated = real['stack'][:, 1:, :]
    losses = ((generated == 0) & (baseline == 1)).all(axis=0)
    wins = ((generated == 1) & (baseline == 0)).all(axis=0)
    observed = {}
    for label, matches in [('loss', losses), ('win', wins)]:
        tasks = matches.any(axis=0)
        count = int(tasks.sum())
        assert count == base.D['repeatability']['eval_real']['all_repeat_patterns'][label+'_tasks']
        observed[label] = {'tasks': count, 'member_task_pairs': int(matches.sum()),
                           'task_ids': real['tasks'][tasks].tolist()}
    assert observed['win']['task_ids'] == ['math500_split#379']
    example = 'math500_split#138'
    example_index = real['tasks'].tolist().index(example)
    evidence = {
        'matrix_sha256': MATRIX_HASHES,
        'axes': ['repeat', 'member_or_slot', 'task'],
        'score_semantics': 'Recorded binary correctness, not latent reasoning ability.',
        'aggregate_pattern_semantics': (
            'At least one generated member has the stated score contrast against '
            'baseline on that task in all three repeats. Each count-grid square '
            'represents one task. The loss glyphs explain its aggregate definition.'),
        'persistent_patterns': observed,
        'example_task': example,
        'example_selection': (
            'Chosen after examining outcomes to illustrate persistent scored '
            'weaknesses and variable same-code executions. It is not random or '
            'representative and does not compute the population residual r.'),
        'example': {name: {'member_order': arm['members'].tolist(),
                           'scores_by_repeat': arm['stack'][:, :, example_index].astype(int).tolist()}
                    for name, arm in arms.items()},
        'held_out_difference': {
            'definition': 'D = G_generated - G_same_code',
            'G_generated': base.D['primary']['G'],
            'G_same_code': base.D['primary']['paired_difference']['G_clone'],
            'D': base.D['primary']['paired_difference']['D_real_minus_clone'],
            'warning': 'D is not the difference between the two plugin headroom bars.'},
    }
    assert abs(evidence['held_out_difference']['G_generated'] -
               evidence['held_out_difference']['G_same_code'] -
               evidence['held_out_difference']['D']) < 1e-10
    (OUT / 'evidence_audit.json').write_text(json.dumps(evidence, indent=2)+'\n')
    return evidence


def compare_with_v6():
    """The accepted reference and revisions, each at native manuscript width."""
    with fitz.open() as sheet, fitz.open() as raw:
        page = sheet.new_page(width=612, height=1024)
        page.insert_font(fontname='stix', fontfile=str(base.FONTS / 'STIXGeneral.ttf'))
        page.insert_font(fontname='bold', fontfile=str(base.FONTS / 'STIXGeneralBol.ttf'))
        page.insert_text((108, 25), 'V8 — content improvements against v6',
                         fontname='bold', fontsize=12)
        entries = [('V6 reference', HERE / 'output/v6/teaser_illustrated.pdf')]
        entries += [(f'{key} · {spec["label"]}', OUT / f'teaser_{spec["stem"]}.pdf')
                    for key, spec in CANDIDATES.items()]
        placements = []
        for i, (label, path) in enumerate(entries):
            top = 53 + i*232
            page.insert_text((108, top-8), label, fontname='bold', fontsize=9)
            rect = fitz.Rect(108, top, 504, top+198)
            with fitz.open(path) as figure:
                page.show_pdf_page(rect, figure, 0)
                if i:
                    raw.insert_pdf(figure)
            placements.append({'label': label, 'source': str(path.relative_to(HERE)),
                               'figure_rect_pt': list(rect), 'scale': 1.0})
        page.insert_text((108, 988), 'All figures: 396 × 198 pt · same six result groups · no global title',
                         fontname='stix', fontsize=8, color=(.35, .4, .45))
        sheet.save(OUT / 'comparison_with_v6.pdf', garbage=4, deflate=True)
        page.get_pixmap(matrix=fitz.Matrix(1.3, 1.3), alpha=False).save(
            OUT / 'comparison_with_v6.preview.png')
        raw.save(OUT / 'teasers_all.pdf', garbage=4, deflate=True)
    return placements


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', choices=CANDIDATES)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    archive = OUT / 'previous_versions_manifest.json'
    if not archive.exists():
        files = {str(p.relative_to(HERE)): sha(p)
                 for version in range(1, 8)
                 for p in sorted((HERE / f'output/v{version}').rglob('*')) if p.is_file()}
        archive.write_text(json.dumps(files, indent=2)+'\n')
    files = json.loads(archive.read_text())
    assert all(sha(HERE / name) == expected for name, expected in files.items())
    evidence = audit_evidence()
    results = []
    for key, spec in CANDIDATES.items():
        if args.only and args.only != key:
            continue
        module = importlib.import_module(spec['module'])
        with base.plt.rc_context({'svg.hashsalt': 'ai4ai-teaser-v8'}):
            fig = module.draw()
            path = OUT / f'teaser_{spec["stem"]}.pdf'
            fig.savefig(path, metadata={'Title': '', 'Author': '', 'CreationDate': None,
                'ModDate': None, 'Subject': spec['label']})
            svg = path.with_suffix('.svg')
            fig.savefig(svg, metadata={'Date': None})
            svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
            ET.parse(svg)
            base.plt.close(fig)
        report = inspect_pdf(path)
        report.update({'candidate': key, 'concept': spec['label']})
        results.append(report)
        print(json.dumps(report, indent=2), flush=True)
    if args.only:
        return
    comparison = compare_with_v6()
    assert all(sha(HERE / name) == expected for name, expected in files.items())
    (OUT / 'provenance.json').write_text(json.dumps({
        'version': 'v8', 'reference': 'v6', 'branch': 'jzsawyer-dev/teaser-v8',
        'purpose': 'Explain the control, persistent score patterns, and held-out correction.',
        'data_source': str(base.SOURCE.relative_to(ROOT)), 'data_sha256': sha(base.SOURCE),
        'reviewed_manuscript_commit': '782bacec0579a4e2ccfea956999235af74ce3bee',
        'v6_pr': 'https://github.com/StatXzy7/AI4AI-Harness/pull/2',
        'v6_pr_merged_at': '2026-09-26T10:22:24Z',
        'old_version_files_unchanged': len(files),
        'evidence_audit': 'evidence_audit.json',
        'data_transformations': ['Display rounding only for the six retained result groups.',
                                'Persistent-pattern counts reproduced from full binary tensors.',
                                'B displays one deliberately chosen task; no data interpolation.'],
        'illustration_semantics': {
            'A': 'Original whole schematic bitmap; count grid and vector loss-pattern definition.',
            'B': 'Vector schematic code motifs and actual binary observations for example #138.',
            'C': 'Original whole schematic bitmap; two-member population-probability schematics, not measured curves.'},
        'font': 'Embedded STIX General, 7.5 pt minimum.',
        'comparison': comparison, 'outputs': results,
    }, indent=2)+'\n')
    (OUT / 'validation.json').write_text(json.dumps({
        'source_values_checked': True, 'tensor_hashes_checked': True,
        'persistent_counts_reproduced': {k: v['tasks'] for k, v in evidence['persistent_patterns'].items()},
        'previous_version_files_unchanged': len(files), 'outputs': results,
    }, indent=2)+'\n')


if __name__ == '__main__':
    main()
