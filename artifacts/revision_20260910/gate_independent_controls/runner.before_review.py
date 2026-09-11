"""Measure frozen independently authored controls once; no model/provider calls."""
import hashlib
import importlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from experiment.revision.gate_v2 import SCHEMA, STRATEGIES, evaluate, scenarios

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/revision_20260910/gate_independent_controls'
SALT = 'independent-v1-20260910'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def main():
    freeze = json.loads((OUT / 'measurement_freeze.json').read_text(encoding='utf-8'))
    for name, expected in freeze['bindings'].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f'Frozen input changed: {name}')
    if any((OUT / name).exists() for name in ('results.json', 'review_packet.json', 'measurement_started.json')):
        raise FileExistsError('Measurement evidence already exists; do not replace or automatically rerun')
    module = importlib.import_module('experiment.revision.independent_gate_controls')
    controls = module.CASES
    counts = Counter(c['strategy'] for c in controls)
    if len(controls) != 32 or len({c['case_id'] for c in controls}) != 32 or counts != Counter({s: 4 for s in STRATEGIES}):
        raise ValueError('Expected exactly 32 unique controls, four per strategy')
    source_path = ROOT / 'experiment/revision/independent_gate_controls.py'
    source = source_path.read_text(encoding='utf-8')
    write_new(OUT / 'measurement_started.json', {
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'measurement_freeze_sha256': sha(OUT / 'measurement_freeze.json'),
        'salt': SALT, 'planned_cases': 32})
    rows, packet = [], []
    for control in controls:
        result = evaluate(control['solve'], control['strategy'], salt=SALT)
        identity = {'case_id': control['case_id'], 'strategy': control['strategy'],
                    'callable_name': control['solve'].__name__}
        rows.append({**identity, **result})
        probes = {p.name: p for p in scenarios(control['strategy'], salt=SALT)}
        # No automatic verdict, reasons, or author-reference labels are exposed.
        runs = [{'probe': r['probe'], 'question': probes[r['probe']].question,
                 'trace': r['trace'], 'final': r['final'], 'error': r['error']}
                for r in result['runs'] if r['probe'] in probes]
        runs_hash = hashlib.sha256(json.dumps(runs, sort_keys=True, ensure_ascii=False,
                                             separators=(',', ':')).encode('utf-8')).hexdigest()
        packet.append({**identity, 'schema': SCHEMA, 'runs': runs, 'runs_sha256': runs_hash})
    for name, expected in freeze['bindings'].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f'Frozen input changed during measurement: {name}')
    common = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
              'measurement_freeze_sha256': sha(OUT / 'measurement_freeze.json'),
              'source_sha256': sha(source_path), 'salt': SALT,
              'scope': 'independently authored synthetic controls, not benchmark or population error rates'}
    write_new(OUT / 'results.json', {**common, 'cases': rows})
    write_new(OUT / 'review_packet.json', {**common, 'source': source, 'cases': packet})
    print(json.dumps({'cases': len(rows), 'structural_states': dict(Counter(r['verdict'] for r in rows))}))


if __name__ == '__main__':
    main()
