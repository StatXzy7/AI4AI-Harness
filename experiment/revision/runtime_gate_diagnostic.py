"""One retained diagnostic of seven archived candidates with the frozen v3 gate.

Selection is source-only and fixed by the stage22 manifest. Missing format_guard
is retained as unavailable. Synthetic outcomes do not admit or score candidates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from experiment.revision.gate_runtime_adapter import candidate
from experiment.revision import gate_v3
from experiment.revision.common_pool import publish
from experiment.revision.replay import ROOT

SOURCE_MANIFEST = 'artifacts/revision_20260910/runtime_gate_bridge/source_manifest.json'
PROTOCOL = 'review-stage/RUNTIME_GATE_DIAGNOSTIC_PROTOCOL.md'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(output):
    output = Path(output).resolve()
    manifest = json.loads((ROOT / SOURCE_MANIFEST).read_text(encoding='utf-8'))
    inputs = [SOURCE_MANIFEST, PROTOCOL, 'experiment/revision/runtime_gate_diagnostic.py',
              'experiment/revision/gate_runtime_adapter.py', 'experiment/revision/gate_v3.py',
              'experiment/revision/gate_v2.py', 'experiment/revision/common_pool.py',
              'experiment/phase2/generate.py', 'review-stage/GATE_V2_CONTRACTS.md',
              'external/TTHE/text_to_sql/harness_base.py', 'external/TTHE/ase/llm.py']
    for case in manifest['cases']:
        if case['path']:
            if sha(ROOT / case['path']) != case['sha256']:
                raise ValueError('archived candidate changed: ' + case['path'])
            inputs.append(case['path'])
    bindings = {name: sha(ROOT / name) for name in inputs}
    output.mkdir(parents=True, exist_ok=False)
    publish(output / 'manifest.json', dict(bindings=bindings, salt='runtime_bridge_stage24',
                                         selection=manifest, scope=__doc__))
    results = []
    for case in manifest['cases']:
        if case['path'] is None:
            result = dict(strategy=case['strategy'], availability='unavailable', result=None)
        else:
            with candidate(ROOT / case['path']) as solve:
                observation = gate_v3.evaluate(solve, case['strategy'], salt='runtime_bridge_stage24')
            result = dict(strategy=case['strategy'], path=case['path'], availability='available',
                          result=observation, admission='not_evaluated')
        publish(output / (case['strategy'] + '.json'), result)
        results.append(result)
    changed = [name for name, expected in bindings.items() if sha(ROOT / name) != expected]
    if changed:
        publish(output / 'INVALID.json', dict(changed=changed))
        raise RuntimeError('input drift during diagnostic; retain incomplete evidence')
    publish(output / 'results.json', results)
    publish(output / 'COMPLETE.json', dict(results_sha256=sha(output / 'results.json'),
                                         manifest_sha256=sha(output / 'manifest.json'),
                                         salt='runtime_bridge_stage24', result_count=len(results),
                                         available=sum(r['availability'] == 'available' for r in results),
                                         scope='finite archived-source interface diagnostic; no calibration or admission'))
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    rows = collect(args.output)
    print(json.dumps({r['strategy']: r['result']['verdict'] if r['result'] else 'unavailable'
                      for r in rows}, indent=2))
