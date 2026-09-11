"""Retain the fixed 11 source-assigned runtime response-profile diagnostics."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

from experiment.revision.common_pool import file_hash, publish
from experiment.revision.gate_runtime_adapter import candidate
from experiment.revision.replay import ROOT
from experiment.revision.runtime_response_profiles import run, settings


def collect(output):
    output = Path(output).resolve()
    roster_path = ROOT / 'artifacts/revision_20260910/runtime_gate_bridge/source_manifest.json'
    roster = json.loads(roster_path.read_text(encoding='utf-8'))
    cases = settings()
    selected = {r['strategy']: r for r in roster['cases'] if r['strategy'] in {c['strategy'] for c in cases}}
    paths = [roster_path, Path(__file__), ROOT / 'experiment/revision/runtime_response_profiles.py',
             ROOT / 'experiment/revision/gate_runtime_adapter.py', ROOT / 'experiment/revision/gate_v2.py',
             ROOT / 'experiment/revision/gate_v3.py', ROOT / 'experiment/revision/common_pool.py',
             ROOT / 'external/TTHE/text_to_sql/harness_base.py', ROOT / 'external/TTHE/ase/llm.py',
             ROOT / 'review-stage/RUNTIME_RESPONSE_PROFILES_PROTOCOL.md']
    for row in selected.values():
        if file_hash(ROOT / row['path']) != row['sha256']:
            raise ValueError('archived source changed: ' + row['path'])
        paths.append(ROOT / row['path'])
    bindings = {p.relative_to(ROOT).as_posix(): file_hash(p) for p in paths}
    output.mkdir(parents=True, exist_ok=False)
    publish(output / 'manifest.json', dict(bindings=bindings, cases=cases, sources=selected,
                                         sqlite_version=sqlite3.sqlite_version, python=sys.version))
    results = []
    for case in cases:
        with candidate(ROOT / selected[case['strategy']]['path']) as solve:
            result = run(solve, case)
        publish(output / (case['name'] + '.json'), result)
        results.append(result)
    changed = [name for name, expected in bindings.items() if file_hash(ROOT / name) != expected]
    if changed:
        publish(output / 'INVALID.json', dict(changed=changed))
        raise RuntimeError('input drift during diagnostic')
    publish(output / 'results.json', results)
    publish(output / 'COMPLETE.json', dict(results_sha256=file_hash(output / 'results.json'),
                                         manifest_sha256=file_hash(output / 'manifest.json'),
                                         scenarios=len(results), admission='not_evaluated'))
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    results = collect(args.output)
    print(json.dumps({r['case']['name']: dict(error=r['error'], interface_issues=r['interface_issues'])
                      for r in results}, indent=2))
