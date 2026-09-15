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
EXPECTED = {'eval_real': 10800, 'eval_clone': 10800, 'dev_real': 2700}


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arms', default='eval_real,eval_clone,dev_real')
    args = ap.parse_args()
    out = {}
    for arm in args.arms.split(','):
        out[arm] = seal(arm.strip())
        print(json.dumps(out[arm], ensure_ascii=False))
    (WP1R / 'seal_report.json').write_text(json.dumps(out, indent=1, ensure_ascii=False),
                                           encoding='utf-8')


if __name__ == '__main__':
    main()
