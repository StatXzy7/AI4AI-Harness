"""One frozen v4 reference measurement and label-free source/trace packaging."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import inspect
import json
from pathlib import Path
import re

from experiment.revision import gate_v3, gate_v4
from experiment.revision.common_pool import ROOT, file_hash, publish

TRACE_FIELDS = {'kind', 'prompt', 'system', 'temperature', 'n', 'response', 'seq',
                'sql', 'ok', 'rows', 'error', 'error_type'}


def validate(freeze, output):
    if (output / 'INVALID.json').exists():
        raise ValueError('measurement marked invalid')
    changed = [name for name, digest in freeze['bindings'].items()
               if not (ROOT / name).is_file() or file_hash(ROOT / name) != digest]
    if changed:
        if output.exists():
            publish(output / 'INVALID.json', dict(changed=changed))
        raise ValueError('frozen input changed')


def review_runs(result, strategy, salt):
    """Export actual events without instrumentation roles, targets or verdicts."""
    runs = []
    for run in result['runs']:
        if 'case' in run:
            name = run['case']['name']
            question = gate_v3.QUESTION
        else:
            name = run['probe']
            question = next(p.question for p in gate_v3.scenarios(strategy, salt) if p.name == name)
        runs.append(dict(probe=name, question=question,
                         trace=[{k:v for k,v in event.items() if k in TRACE_FIELDS} for event in run['trace']],
                         final=run['final'], error=run['error']))
    return runs


def validate_dependencies(freeze):
    required = {'experiment/revision/gate_v4.py', 'experiment/revision/gate_v3.py',
                'experiment/revision/gate_v2.py', 'experiment/revision/runtime_response_profiles.py',
                'experiment/revision/independent_gate_v4_measure.py',
                'experiment/revision/common_pool.py', 'experiment/revision/code_responses.py',
                'experiment/revision/fresh_runtime.py',
                'experiment/phase2/generate.py',
                'review-stage/GATE_V4_CALIBRATION_PROTOCOL.md'}
    required.update(freeze[k] for k in ('source_path', 'inventory_path', 'author_reference_path',
                                      'source_review_path', 'instrument_freeze_path'))
    if not required.issubset(freeze['bindings']):
        raise ValueError('required measurement dependencies are not bound')
    instrument = json.loads((ROOT / freeze['instrument_freeze_path']).read_text(encoding='utf-8'))
    if any(freeze['bindings'].get(name) != digest for name, digest in instrument['bindings'].items()):
        raise ValueError('measurement disagrees with frozen instrument bindings')


def measure(freeze_path):
    freeze_path = Path(freeze_path).resolve()
    freeze = json.loads(freeze_path.read_text(encoding='utf-8'))
    freeze_hash = file_hash(freeze_path)
    validate_dependencies(freeze)
    output = ROOT / freeze['output']
    validate(freeze, output)
    if output.exists():
        raise FileExistsError('measurement output already exists')
    roster = freeze['roster']
    if (len(roster) != 32 or len({r['case_id'] for r in roster}) != 32
            or Counter(r['strategy'] for r in roster) != Counter({s: 4 for s in gate_v4.STRATEGIES})):
        raise ValueError('expected exactly four controls per strategy')
    if any(set(r) != {'case_id', 'strategy', 'callable_name', 'profile'}
           or not re.fullmatch(r'[A-Za-z0-9_]+', r['case_id']) for r in roster):
        raise ValueError('neutral identity fields and safe case ids required')
    source_path = ROOT / freeze['source_path']
    spec = importlib.util.spec_from_file_location('_frozen_v4_references', source_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for item in roster:
        inspect.signature(getattr(module, item['callable_name'])).bind(object(), 'question')
    output.mkdir(parents=True, exist_ok=False)
    publish(output / 'manifest.json', dict(freeze_sha256=freeze_hash, freeze=freeze))
    rows = []
    packet = []
    for item in roster:
        validate(freeze, output)
        if file_hash(freeze_path) != freeze_hash:
            publish(output / 'INVALID.json', dict(reason='measurement freeze changed'))
            raise ValueError('measurement freeze changed')
        try:
            result = gate_v4.evaluate(getattr(module, item['callable_name']), item['strategy'],
                                      profile=item['profile'], salt=freeze['salt'])
        except Exception as exc:
            result = dict(structural_verdict='execution_failure', runs=[],
                          measurement_error=f'{type(exc).__name__}: {exc}')
        row = dict(identity=item, result=result)
        publish(output / (item['case_id'] + '.json'), row)
        rows.append(row)
        runs = review_runs(result, item['strategy'], freeze['salt'])
        packet.append(dict(identity=item, schema=gate_v3.SCHEMA, runs=runs,
                           measurement_error=result.get('measurement_error')))
    validate(freeze, output)
    if file_hash(freeze_path) != freeze_hash:
        publish(output / 'INVALID.json', dict(reason='measurement freeze changed'))
        raise ValueError('measurement freeze changed')
    publish(output / 'results.json', rows)
    publish(output / 'review_packet.json', dict(source=source_path.read_text(encoding='utf-8'),
                                               source_sha256=file_hash(source_path), cases=packet,
                                               scope='source and actual traces only; hidden labels and automatic conclusions'))
    if sum(len(r['result']['runs']) for r in rows) != freeze['planned_scenarios']:
        publish(output / 'INVALID.json', dict(reason='planned scenario count mismatch'))
        raise RuntimeError('planned scenario count mismatch')
    publish(output / 'COMPLETE.json', dict(freeze_sha256=freeze_hash,
                                         manifest_sha256=file_hash(output / 'manifest.json'),
                                         results_sha256=file_hash(output / 'results.json'),
                                         packet_sha256=file_hash(output / 'review_packet.json'), cases=32))
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args()
    rows = measure(args.freeze)
    print(json.dumps(dict(Counter(row['result']['structural_verdict'] for row in rows)), indent=2))
