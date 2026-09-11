"""Replay exposed controls against v3; never overwrite the first v2 measurement."""
import hashlib
import json
from collections import Counter
from pathlib import Path

from experiment.revision import gate_v3
from experiment.revision.independent_gate_controls import CASES

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / 'artifacts/revision_20260910/gate_independent_controls'
OUT = ROOT / 'artifacts/revision_20260910/gate_v3_repair/regression.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUT.exists():
        raise FileExistsError('Keep existing regression evidence; choose a new version after changes.')
    old = json.loads((OLD / 'results.json').read_text(encoding='utf-8'))
    references = json.loads((OLD / 'summary.json').read_text(encoding='utf-8'))
    freeze = json.loads((OLD / 'measurement_freeze.json').read_text(encoding='utf-8'))
    for name in ('experiment/revision/gate_v2.py', 'experiment/revision/independent_gate_controls.py'):
        if digest(ROOT / name) != freeze['bindings'][name]:
            raise ValueError('Frozen input changed: ' + name)
    for name, expected in references['bindings'].items():
        if digest(ROOT / name) != expected:
            raise ValueError('Historical reference changed: ' + name)
    inputs = [ROOT / name for name in (
        'experiment/revision/gate_v2.py', 'experiment/revision/gate_v3.py',
        'experiment/revision/independent_gate_controls.py',
        'experiment/revision/gate_v3_report.py', 'review-stage/GATE_V3_REPAIR.md')]
    inputs += [OLD / name for name in ('results.json', 'summary.json', 'measurement_freeze.json')]
    bindings = {p.relative_to(ROOT).as_posix(): digest(p) for p in inputs}
    identifiers = [c['case_id'] for c in CASES]
    if (len(identifiers) != 32 or len(set(identifiers)) != 32 or
            identifiers != [c['case_id'] for c in old['cases']] or
            identifiers != [c['case_id'] for c in references['rows']]):
        raise ValueError('Exposed-control roster mismatch')
    rows = []
    for case, previous, reference in zip(CASES, old['cases'], references['rows']):
        if case['strategy'] != previous['strategy'] or case['strategy'] != reference['strategy']:
            raise ValueError('Exposed-control strategy mismatch')
        result = gate_v3.evaluate(case['solve'], case['strategy'], old['salt'])
        rows.append(dict(case_id=case['case_id'], strategy=case['strategy'],
                         previous_structural_state=previous['verdict'],
                         historical_reference=reference, v3=result))
    for name, expected in bindings.items():
        if digest(ROOT / name) != expected:
            raise ValueError('Input changed during replay: ' + name)
    output = dict(scope='Exposed-control regression, not independent calibration or admission',
                  bindings=bindings, salt=old['salt'], cases=rows,
                  structural_counts=dict(Counter(r['v3']['verdict'] for r in rows)),
                  transitions=[dict(case_id=r['case_id'], old=r['previous_structural_state'],
                                    new=r['v3']['verdict']) for r in rows
                               if r['previous_structural_state'] != r['v3']['verdict']],
                  historical_adjudication_reused_for_admission=False,
                  production_admissions=0, external_generation_requests=0)
    with OUT.open('x', encoding='utf-8') as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps(output['structural_counts'], sort_keys=True))
    print(json.dumps(output['transitions'], sort_keys=True))


if __name__ == '__main__':
    main()
