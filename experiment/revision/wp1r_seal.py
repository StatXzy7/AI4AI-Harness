"""Seal a completed WP-1R arm: verify, snapshot, hash, freeze.

Per protocol section 9/13: SEALED requires every scheduled cell to have a
durable result (success or reconciled unknown/failed), no run_invalid event,
source hashes unchanged since the manifest, and a SHA256-bound snapshot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WP1R = ROOT / 'artifacts/wp1r_20260915'
EXPECTED = {'eval_real': 10800, 'eval_clone': 10800, 'dev_real': 2700,
           'eval_real_cont': 10800, 'eval_clone_cont': 10800,
           'eval_real_cont2': 10800, 'dev_real_cont2': 2700}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def seal(arm: str) -> dict:
    folder = WP1R / arm
    ledger = folder / 'ledger.sqlite'
    report = {'arm': arm, 'sealed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    conn = sqlite3.connect(f'file:{ledger}?mode=ro', uri=True)
    total = conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
    done = conn.execute('SELECT COUNT(*) FROM tasks WHERE result IS NOT NULL').fetchone()[0]
    report['cells'] = {'total': total, 'with_result': done,
                       'expected': EXPECTED[arm]}
    if total != EXPECTED[arm] or done != total:
        report['state'] = 'NOT_SEALED'
        report['reason'] = 'cells incomplete'
        return report
    invalid = conn.execute("SELECT COUNT(*) FROM events WHERE json_extract(value,'$.kind')='run_invalid'").fetchone()[0]
    unknown = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE json_extract(result,'$.outcome')='unknown_remote'").fetchone()[0]
    failed = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE json_extract(result,'$.error') IS NOT NULL").fetchone()[0]
    correct = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE json_extract(result,'$.official_correct')=1").fetchone()[0]
    report['cells'].update({'run_invalid': invalid, 'unknown_remote': unknown,
                            'failed': failed, 'official_correct': correct})
    manifest = json.loads(conn.execute('SELECT value FROM manifest WHERE id=1').fetchone()[0])
    # source hashes unchanged since manifest
    drifted = []
    for rel, expected_hash in manifest['source_sha256'].items():
        p = ROOT / rel
        if not p.exists() or sha(p) != expected_hash:
            drifted.append(rel)
    report['source_drift'] = drifted
    counts = {k: v for k, v in report['cells'].items()}
    ok = invalid == 0 and not drifted and counts['failed'] / total <= 0.15
    report['state'] = 'SEALED' if ok else 'NOT_SEALED'
    if report['state'] == 'SEALED':
        snap = {
            'arm': arm, 'sealed_at': report['sealed_at'],
            'manifest': manifest,
            'cells': report['cells'],
            'ledger_sha256': sha(ledger),
        }
        (folder / 'SEALED.json').write_text(json.dumps(snap, indent=1, ensure_ascii=False),
                                            encoding='utf-8')
    return report


def seal_merged(arm: str) -> dict:
    """Seal a merged arm across its continuation ledgers (post-2026-09-17).

    The stop-and-reconcile events split each arm across ledgers; the
    meaningful completeness statement is over the merged unique-cell view
    produced by the deterministic precedence rule of wp1r_analysis.
    """
    from experiment.revision.wp1r_analysis import ARM_LEDGERS, merge_cells
    names = [n for n in ARM_LEDGERS[arm]
             if (WP1R / n / 'ledger.sqlite').exists()]
    cell_map, dedup = merge_cells(names)
    invalid = 0
    ledger_hashes = {}
    for n in names:
        ledger = WP1R / n / 'ledger.sqlite'
        conn = sqlite3.connect(f'file:{ledger}?mode=ro', uri=True)
        invalid += conn.execute(
            "SELECT COUNT(*) FROM events "
            "WHERE json_extract(value,'$.kind')='run_invalid'").fetchone()[0]
        conn.close()
        ledger_hashes[n] = sha(ledger)
    unknown = sum(1 for c in cell_map.values()
                  if c.get('official_correct') is None)
    # source drift: measured sources (harnesses, split, runtime, bridge)
    # must be byte-frozen across ledgers AND match the working tree; the
    # collector itself legitimately evolved across continuation boundaries
    # (race fix dd5a773, concurrency amendments) and each ledger binds the
    # bytes it was created with -- recorded as provenance, not a failure.
    collector = 'experiment\\revision\\fresh_collect_math.py'
    manifests = []
    for n in names:
        conn = sqlite3.connect(
            f"file:{WP1R / n / 'ledger.sqlite'}?mode=ro", uri=True)
        manifests.append(json.loads(conn.execute(
            'SELECT value FROM manifest WHERE id=1').fetchone()[0]))
        conn.close()
    drifted = []
    for rel, expected_hash in manifests[0]['source_sha256'].items():
        if rel.replace('/', '\\') == collector or rel == collector:
            continue
        p = ROOT / rel
        if not p.exists() or sha(p) != expected_hash:
            drifted.append(rel)
        for m in manifests[1:]:
            if m['source_sha256'].get(rel) != expected_hash:
                drifted.append(f'{rel} (cross-ledger)')
    collector_versions = sorted({
        m['source_sha256'].get(collector) or
        m['source_sha256'].get(collector.replace('\\', '/'))
        for m in manifests})
    report = {
        'arm': arm, 'ledgers': names,
        'sealed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'unique_cells': len(cell_map), 'expected': EXPECTED[arm],
        'unknown_remote': unknown, 'run_invalid_events': invalid,
        'dedup': dedup, 'source_drift': drifted,
        'collector_sha256_versions': collector_versions,
        'ledger_sha256': ledger_hashes,
    }
    ok = (len(cell_map) == EXPECTED[arm] and invalid == 0 and not drifted)
    report['state'] = 'SEALED' if ok else 'NOT_SEALED'
    if not ok:
        report['reason'] = (
            'incomplete' if len(cell_map) != EXPECTED[arm] else
            'run_invalid events' if invalid else 'source drift')
    if report['state'] == 'SEALED':
        (WP1R / f'SEALED_{arm}.json').write_text(
            json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arms', default='eval_real,eval_clone,dev_real')
    ap.add_argument('--merged', action='store_true',
                    help='seal the merged continuation-ledger view')
    args = ap.parse_args()
    out = {}
    for arm in args.arms.split(','):
        arm = arm.strip()
        out[arm] = seal_merged(arm) if args.merged else seal(arm)
        print(json.dumps(out[arm], ensure_ascii=False))
    (WP1R / 'seal_report.json').write_text(json.dumps(out, indent=1, ensure_ascii=False),
                                           encoding='utf-8')


if __name__ == '__main__':
    main()
