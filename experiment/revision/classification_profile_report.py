"""Collect a fixed, exposed-control response-profile regression report."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

from experiment.revision import gate_v3
from experiment.revision.classification_profiles import PROFILES, run_profile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/revision_20260910/classification_profiles'
SOURCE = ROOT / 'experiment/revision/independent_gate_v3_controls.py'
EXPECTED_CASES = ('vc025', 'vc026', 'vc027', 'vc028')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    with temporary.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    # Publish complete bytes without replacing an existing measurement.
    os.link(temporary, path)
    temporary.unlink()


def load_roles():
    roles = json.loads((OUT / 'role_map.json').read_text(encoding='utf-8'))
    if roles['source_sha256'] != digest(SOURCE):
        raise ValueError('role map source hash mismatch')
    if roles['protocol_sha256'] != digest(OUT / 'PROTOCOL.md'):
        raise ValueError('role map protocol hash mismatch')
    mapped = roles['cases']
    if len(mapped) != 4 or {case['case_id'] for case in mapped} != set(EXPECTED_CASES):
        raise ValueError('role map must cover the four fixed cases exactly once')
    if any(case['role'] not in (*PROFILES, 'ambiguous') for case in mapped):
        raise ValueError('unsupported source-assigned role')
    return {case['case_id']: case['role'] for case in mapped}


def collect():
    roles = load_roles()
    paths = [SOURCE, Path(gate_v3.__file__), Path(__file__),
             ROOT / 'experiment/revision/classification_profiles.py',
             OUT / 'PROTOCOL.md', OUT / 'role_map.json']
    bindings = {path.relative_to(ROOT).as_posix(): digest(path) for path in paths}
    # Refuse a second traversal; the map and implementation are bound before import/run.
    write_new(OUT / 'measurement_freeze.json', dict(bindings=bindings, roles=roles,
              scope='exposed-control development regression', salt='independent-v3-20260910'))
    from experiment.revision.independent_gate_v3_controls import CASES
    controls = {case['case_id']: case for case in CASES if case['case_id'] in roles}
    cases = []
    for case_id in EXPECTED_CASES:
        solve = controls[case_id]['solve']
        role = roles[case_id]
        variants = [(profile, None) for profile in PROFILES]
        if role == 'classify_then_repair':
            variants.extend([('classify_then_repair', 'UNRECOGNIZED_CATEGORY'),
                             ('classify_then_repair', 'syntax or schema')])
        profiles = []
        for profile, reply in variants:
            primary = role == profile and reply is None
            runs = [run_profile(solve, probe, profile, reply)
                    for probe in gate_v3.scenarios('error_classify', 'independent-v3-20260910')]
            profiles.append(dict(profile=profile, category_override=reply,
                                 use='primary' if primary else 'diagnostic', runs=runs))
        cases.append(dict(case_id=case_id, source_assigned_role=role,
                          status='review_required', profiles=profiles))
    # No merge, best-profile selection or automatic admission is performed here.
    results = dict(scope='exposed-control development regression', cases=cases,
                   freeze_sha256=digest(OUT / 'measurement_freeze.json'))
    write_new(OUT / 'results.json', results)
    complete_saved()
    return results


def complete_saved():
    """Finish packaging complete saved results without executing any profile."""
    if (OUT / 'INVALID.json').exists():
        raise RuntimeError('collection was invalidated; restoring inputs cannot make it complete')
    freeze = json.loads((OUT / 'measurement_freeze.json').read_text(encoding='utf-8'))
    changed = [path for path, value in freeze['bindings'].items() if digest(ROOT / path) != value]
    if changed:
        write_new(OUT / 'INVALID.json', dict(reason='bound input changed', paths=changed))
        raise RuntimeError('bound input changed during collection; results are not complete')
    if load_roles() != freeze['roles']:
        raise ValueError('frozen role mapping mismatch')
    results = json.loads((OUT / 'results.json').read_text(encoding='utf-8'))
    if results['freeze_sha256'] != digest(OUT / 'measurement_freeze.json'):
        raise ValueError('saved results freeze mismatch')
    complete = dict(results_sha256=digest(OUT / 'results.json'), freeze_sha256=results['freeze_sha256'])
    if (OUT / 'COMPLETE.json').exists():
        if json.loads((OUT / 'COMPLETE.json').read_text(encoding='utf-8')) != complete:
            raise ValueError('saved completion hash mismatch')
    else:
        write_new(OUT / 'COMPLETE.json', complete)
    return complete


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-only', action='store_true')
    args = parser.parse_args()
    complete_saved() if args.package_only else collect()
