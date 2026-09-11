"""Measure frozen independently authored controls once; no model/provider calls."""
import hashlib
import importlib
import inspect
import json
import os
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from experiment.revision.gate_v3 import SCHEMA, STRATEGIES, evaluate, scenarios

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/revision_20260910/gate_v3_independent'
SALT = 'independent-v3-20260910'
SEMANTIC = ('hint_guard', 'format_guard', 'two_view', 'error_classify', 'decompose')
REQUIRED = ('experiment/revision/gate_v3.py', 'experiment/revision/independent_gate_v3_controls.py',
            'experiment/revision/independent_gate_v3_measure.py', 'artifacts/revision_20260910/gate_v3_independent/CONTRACT.md',
            'artifacts/revision_20260910/gate_v3_independent/PROTOCOL.md',
            'artifacts/revision_20260910/gate_v3_independent/author_labels.json')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    if path.exists():
        raise FileExistsError(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.rename(path)


def main():
    freeze = json.loads((OUT / 'measurement_freeze.json').read_text(encoding='utf-8'))
    if (set(freeze['bindings']) != set(REQUIRED) or freeze['salt'] != SALT or freeze['planned_cases'] != 32
            or freeze['strategy_counts'] != {s: 4 for s in STRATEGIES}
            or freeze['semantic_strategies'] != list(SEMANTIC)):
        raise ValueError('Incomplete or incompatible measurement freeze')
    for name, expected in freeze['bindings'].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f'Frozen input changed: {name}')
    package_only = sys.argv[1:] == ['--package-only']
    if sys.argv[1:] and not package_only:
        raise ValueError('Only --package-only is supported')
    if not package_only and any((OUT / name).exists() for name in ('results.json', 'review_packet.json', 'measurement_started.json')):
        raise FileExistsError('Measurement evidence already exists; do not replace or automatically rerun')
    module = importlib.import_module('experiment.revision.independent_gate_v3_controls')
    controls = module.CASES
    counts = Counter(c['strategy'] for c in controls)
    if len(controls) != 32 or len({c['case_id'] for c in controls}) != 32 or counts != Counter({s: 4 for s in STRATEGIES}):
        raise ValueError('Expected exactly 32 unique controls, four per strategy')
    for c in controls:
        if set(c) != {'case_id', 'strategy', 'solve'} or not isinstance(c['case_id'], str) or not callable(c['solve']):
            raise ValueError('Invalid control schema')
        inspect.signature(c['solve']).bind(object(), 'question')
    roster = [{'case_id': c['case_id'], 'strategy': c['strategy'], 'callable_name': c['solve'].__name__} for c in controls]
    if roster != freeze['case_roster']:
        raise ValueError('Control roster/order changed')
    source_path = ROOT / 'experiment/revision/independent_gate_v3_controls.py'
    source = source_path.read_text(encoding='utf-8')
    if package_only:
        saved = json.loads((OUT / 'results.json').read_text(encoding='utf-8'))
        if saved['measurement_freeze_sha256'] != sha(OUT / 'measurement_freeze.json'):
            raise ValueError('Saved results belong to another freeze')
        rows = saved['cases']
    else:
        write_new(OUT / 'measurement_started.json', {
            'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
            'measurement_freeze_sha256': sha(OUT / 'measurement_freeze.json'),
            'salt': SALT, 'planned_cases': 32})
        rows = []
        for control, identity in zip(controls, roster):
            try:
                result = evaluate(control['solve'], control['strategy'], salt=SALT)
            except Exception as exc:
                result = {'strategy': control['strategy'], 'verdict': 'execution_failure', 'runs': [],
                          'measurement_error': {'stage': 'evaluate', 'type': type(exc).__name__, 'message': str(exc)}}
            rows.append({**identity, **result})
    common = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
              'measurement_freeze_sha256': sha(OUT / 'measurement_freeze.json'),
              'source_sha256': sha(source_path), 'salt': SALT,
              'scope': 'independently authored synthetic controls, not benchmark or population error rates'}
    if package_only:
        for field in ('measurement_freeze_sha256', 'source_sha256', 'salt', 'scope'):
            if saved[field] != common[field]:
                raise ValueError(f'Saved results metadata mismatch: {field}')
        common['recorded_at_utc'] = saved['recorded_at_utc']
    if not package_only:
        write_new(OUT / 'results.json', {**common, 'cases': rows})
    if [{k: r[k] for k in ('case_id', 'strategy', 'callable_name')} for r in rows] != roster:
        raise ValueError('Saved result roster mismatch')
    packet = []
    for result in rows:
        identity = {k: result[k] for k in ('case_id', 'strategy', 'callable_name')}
        probes = {p.name: p for p in scenarios(result['strategy'], salt=SALT)}
        # No automatic verdict, reasons, or author-reference labels are exposed.
        runs = [{'probe': r['probe'], 'question': probes[r['probe']].question if r['probe'] in probes else None,
                 'trace': [{k: v for k, v in event.items() if k not in {
                     'decomposition_step', 'decomposition_candidates', 'decomposition_ambiguous'}}
                     for event in r['trace']], 'final': r['final'], 'error': r['error']}
                for r in result['runs']
                # This conditional, empty meta-run encodes an instrument
                # observation, not an API event. Keep it only in raw results.
                if not (r['probe'] == 'cross_class_action' and not r['trace'])]
        runs_hash = hashlib.sha256(json.dumps(runs, sort_keys=True, ensure_ascii=False,
                                             separators=(',', ':')).encode('utf-8')).hexdigest()
        packet.append({**identity, 'schema': SCHEMA, 'runs': runs, 'runs_sha256': runs_hash,
                       'review_mode': 'semantic' if result['strategy'] in SEMANTIC else 'source_contract',
                       'measurement_error': result.get('measurement_error')})
    for name, expected in freeze['bindings'].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f'Frozen input changed during measurement: {name}')
    if not (OUT / 'review_packet.json').exists():
        write_new(OUT / 'review_packet.json', {**common, 'source': source, 'cases': packet})
    actual = json.loads((OUT / 'review_packet.json').read_text(encoding='utf-8'))
    if actual['cases'] != packet or actual['source'] != source or actual['measurement_freeze_sha256'] != common['measurement_freeze_sha256']:
        raise ValueError('Existing review packet does not match saved measurement')
    write_new(OUT / 'COMPLETE.json', {'measurement_freeze_sha256': common['measurement_freeze_sha256'],
                                    'results_sha256': sha(OUT / 'results.json'),
                                    'review_packet_sha256': sha(OUT / 'review_packet.json'), 'cases': 32})
    print(json.dumps({'cases': len(rows), 'structural_states': dict(Counter(r['verdict'] for r in rows))}))


if __name__ == '__main__':
    main()
