"""Retained v4 development regression: fixed archive roster plus exposed controls."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

from experiment.revision import gate_controls, gate_v4
from experiment.revision.common_pool import file_hash, publish
from experiment.revision.gate_runtime_adapter import candidate
from experiment.revision.replay import ROOT


def collect(output):
    output = Path(output).resolve()
    roster_path = ROOT / 'artifacts/revision_20260910/runtime_gate_bridge/source_manifest.json'
    roster = json.loads(roster_path.read_text(encoding='utf-8'))
    profiles = dict(schema_link='tables_columns_json', decompose='dedicated_current_subquestion',
                    error_classify='local_classifier')
    cases = [dict(id='archive_' + c['strategy'], strategy=c['strategy'], path=c['path'],
                  source_sha256=c.get('sha256'), role='archived_candidate',
                  profile=profiles.get(c['strategy'])) for c in roster['cases']]
    for name, strategy in [('neg_uncond_twocall', 'repair'), ('neg_selectfirst', 'vote3')]:
        cases.append(dict(id=name, strategy=strategy, path=f'external/TTHE/text_to_sql/agents/{name}.py',
                          role='exposed_negative_control', profile=None))
    cases.append(dict(id='development_format', strategy='format_guard',
                      path='experiment/revision/gate_controls.py', role='exposed_development_control', profile=None))
    paths = [roster_path, Path(__file__), ROOT / 'experiment/revision/gate_v4.py',
             ROOT / 'experiment/revision/gate_v3.py', ROOT / 'experiment/revision/gate_v2.py',
             ROOT / 'experiment/revision/runtime_response_profiles.py',
             ROOT / 'experiment/revision/gate_runtime_adapter.py', ROOT / 'experiment/revision/common_pool.py',
             ROOT / 'external/TTHE/text_to_sql/harness_base.py', ROOT / 'external/TTHE/ase/llm.py',
             ROOT / 'review-stage/GATE_V4_CONTRACT.md']
    for case in cases:
        if case['path']:
            path = ROOT / case['path']
            if case.get('source_sha256') and file_hash(path) != case['source_sha256']:
                raise ValueError('archived candidate changed')
            paths.append(path)
    bindings = {p.relative_to(ROOT).as_posix(): file_hash(p) for p in paths}
    output.mkdir(parents=True, exist_ok=False)
    publish(output / 'manifest.json', dict(cases=cases, bindings=bindings, salt='v4_stage26',
                                         sqlite_version=sqlite3.sqlite_version, python=sys.version))
    results = []
    for case in cases:
        if case['path'] is None:
            result = None
        elif case['id'] == 'development_format':
            result = gate_v4.evaluate(gate_controls.format_guard, 'format_guard', salt='v4_stage26')
        else:
            with candidate(ROOT / case['path']) as solve:
                result = gate_v4.evaluate(solve, case['strategy'], profile=case['profile'], salt='v4_stage26')
        row = dict(case=case, result=result, admission='not_evaluated')
        publish(output / (case['id'] + '.json'), row)
        results.append(row)
    changed = [p for p,h in bindings.items() if file_hash(ROOT/p) != h]
    if changed:
        publish(output / 'INVALID.json', dict(changed=changed))
        raise RuntimeError('input changed during regression')
    publish(output / 'results.json', results)
    publish(output / 'COMPLETE.json', dict(results_sha256=file_hash(output / 'results.json'),
                                         manifest_sha256=file_hash(output / 'manifest.json'),
                                         scope='exposed regression only; no calibration or admission'))
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    rows = collect(args.output)
    print(json.dumps({r['case']['id']: r['result']['structural_verdict'] if r['result'] else 'unavailable'
                      for r in rows}, indent=2))
