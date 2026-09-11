"""Joint positive-weight W1 sensitivity; quantiles are NOT confidence intervals.

Keep original database identities, overlapping splits, random subset draws and
observed executions fixed. Refit all selection rules under each shared weight
vector. No provider calls, new outcomes, or independent utility validation.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import random
from pathlib import Path

import numpy as np

from experiment.revision.fingerprint import candidate_records
from experiment.revision.replay import P2, ROOT, digest, load_sources, membership, task_ids, vector
from experiment.revision.selection import METHODS, METRICS, evaluate, selections


def empty_side_probability(split_manifest):
    """Exact bad-sequence count for n database draws with replacement."""
    databases = sorted(set(split_manifest[0]['dev_databases'] + split_manifest[0]['heldout_databases']))
    n = len(databases)
    bad_by_size = [0] * n
    for size in range(1, n + 1):
        for support in itertools.combinations(databases, size):
            if any(not set(support).intersection(s[side]) for s in split_manifest
                   for side in ('dev_databases', 'heldout_databases')):
                bad_by_size[size - 1] += 1
    onto = [sum((-1)**j * math.comb(k, j) * (k-j)**n for j in range(k+1))
            for k in range(1, n+1)]
    numerator = sum(a*b for a, b in zip(bad_by_size, onto))
    return {'bad_supports_by_size': bad_by_size, 'onto_sequences_by_size': onto,
            'bad_sequences': numerator, 'all_sequences': n**n, 'probability': numerator / n**n}


def positive_weights(dbs, n_draws, seed):
    """One hierarchical positive vector per draw, shared by ALL comparisons."""
    dbs = np.asarray(dbs)
    if dbs.ndim != 1 or not len(dbs) or n_draws < 1:
        raise ValueError('Nonempty database identities and positive draw count required')
    rng = np.random.default_rng(seed)
    result = np.empty((n_draws, len(dbs)))
    for db in np.unique(dbs):
        idx = np.flatnonzero(dbs == db)
        db_weight = rng.exponential(size=(n_draws, 1))
        within = rng.exponential(size=(n_draws, len(idx)))
        result[:, idx] = db_weight * len(idx) * within / within.sum(axis=1, keepdims=True)
    if not np.isfinite(result).all() or not (result > 0).all():
        raise ValueError('Positive-weight generation failed; do not silently repair the draw')
    return result


def weighted_choices(pool, dev_weights, k, method):
    """Batched deterministic selection; preserve the reference name tie rules."""
    pool = np.asarray(pool, dtype=float)
    w = np.asarray(dev_weights, dtype=float)
    if (pool.ndim != 2 or w.ndim != 2 or pool.shape[1] != w.shape[1]
            or not 1 <= k <= len(pool) or not np.isin(pool, [0, 1]).all()
            or not np.isfinite(w).all() or (w < 0).any() or (w.sum(axis=1) <= 0).any()):
        raise ValueError('Binary pool and finite nonnegative weights with positive row sums required')
    acc = w @ pool.T / w.sum(axis=1, keepdims=True)
    if method == 'top-acc':
        return np.argsort(-acc, axis=1, kind='stable')[:, :k]
    if method not in METHODS[2:]:
        raise ValueError('Expected a deterministic selection method')
    lam = None if method == 'div-only' else float(method[4:-3])
    rows = np.arange(len(w))
    selected = np.empty((len(w), k), dtype=int)
    selected[:, 0] = len(pool)-1-np.argmax(acc[:, ::-1], axis=1)
    used = np.zeros_like(acc, dtype=bool)
    used[rows, selected[:, 0]] = True
    covered = pool[selected[:, 0]].copy()
    for step in range(1, k):
        # New coverage = old coverage + newly covered task weights.
        oracle = ((w * (1-covered)) @ pool.T + (w*covered).sum(axis=1, keepdims=True)) / w.sum(axis=1, keepdims=True)
        if lam is None:
            score = oracle
        else:
            # Explicit selected-member order matches reference accumulation.
            previous = acc[rows[:, None], selected[:, :step]]
            candidates = np.concatenate([
                np.broadcast_to(previous[:, None, :], (len(w), len(pool), step)),
                acc[:, :, None]], axis=2)
            score = np.ascontiguousarray(candidates).mean(axis=2) + lam * oracle
        score[used] = -np.inf
        selected[:, step] = len(pool)-1-np.argmax(score[:, ::-1], axis=1)
        used[rows, selected[:, step]] = True
        covered = np.maximum(covered, pool[selected[:, step]])
    return selected


def weighted_evaluate(pool, subsets, dev_weights, test_weights, bare=None):
    """B x draws x k subsets; return B x four metrics with canonical dev ties."""
    pool = np.asarray(pool, dtype=float)
    choices = np.sort(np.asarray(subsets), axis=2)
    dw, tw = np.asarray(dev_weights), np.asarray(test_weights)
    if (choices.ndim != 3 or len(choices) != len(dw) or dw.shape != tw.shape
            or dw.shape[1] != pool.shape[1] or not np.isfinite(dw).all()
            or not np.isfinite(tw).all() or (dw < 0).any() or (tw < 0).any()
            or (dw.sum(axis=1) <= 0).any() or (tw.sum(axis=1) <= 0).any()):
        raise ValueError('Compatible nonempty evaluation sides required')
    if bare is not None:
        pool = np.vstack([bare, pool])
        choices = np.concatenate([np.zeros((*choices.shape[:2], 1), dtype=int), choices+1], axis=2)
    dev_acc = dw @ pool.T / dw.sum(axis=1, keepdims=True)
    test_acc = tw @ pool.T / tw.sum(axis=1, keepdims=True)
    rows = np.arange(len(dw))[:, None, None]
    chosen_dev, chosen_test = dev_acc[rows, choices], test_acc[rows, choices]
    best = chosen_test.max(axis=2)
    winner = chosen_dev.argmax(axis=2)
    fixed = np.take_along_axis(chosen_test, winner[:, :, None], axis=2).squeeze(2)
    # Fixed random subsets have the same coverage for every weight draw.
    if np.array_equal(choices, np.broadcast_to(choices[:1], choices.shape)):
        coverage = np.zeros((choices.shape[1], pool.shape[1]))
        for member in range(choices.shape[2]):
            np.maximum(coverage, pool[choices[0, :, member]], out=coverage)
        oracle = tw @ coverage.T / tw.sum(axis=1, keepdims=True)
    else:
        coverage = np.zeros((*choices.shape[:2], pool.shape[1]))
        for member in range(choices.shape[2]):
            np.maximum(coverage, pool[choices[:, :, member]], out=coverage)
        oracle = (coverage * tw[:, None, :]).sum(axis=2) / tw.sum(axis=1, keepdims=True)
    return np.stack([oracle.mean(axis=1), best.mean(axis=1),
                     (oracle-best).mean(axis=1), fixed.mean(axis=1)], axis=1)


def analyze(pools, keys, bare, tasks, reference, weights):
    """All 100 splits share weights; one uniform row audits canonical replay."""
    if weights.shape[1] != len(tasks) or not (weights > 0).all():
        raise ValueError('Shared weights must be positive on every original task')
    dbs = sorted({t.rpartition('#')[0] for t in tasks})
    task_dbs = np.array([t.rpartition('#')[0] for t in tasks])
    rng = random.Random(20260908)
    totals = np.zeros((len(weights), 2, len(METHODS), 2, len(METRICS)))
    schedule_hash = hashlib.sha256()
    # A uniform row must reproduce the reference without overwriting choices.
    uniform_choice_mismatches = 0
    for split_id, split in enumerate(reference['split_manifest']):
        shuffled = dbs[:]
        rng.shuffle(shuffled)
        if set(shuffled[:len(dbs)//2]) != set(split['dev_databases']):
            raise ValueError('RNG schedule differs from the canonical split')
        dev_mask = np.isin(task_dbs, split['dev_databases'])
        dev, heldout = np.flatnonzero(dev_mask), np.flatnonzero(~dev_mask)
        dw, tw = weights * dev_mask, weights * ~dev_mask
        for key in keys:
            pool = pools[key]
            for ki, k in enumerate((4, 8)):
                canonical = selections(pool, k, dev, rng, reference['n_random'])
                schedule_hash.update(json.dumps(canonical['random'], separators=(',', ':')).encode())
                for mi, method in enumerate(METHODS):
                    if method == 'random':
                        choices = np.broadcast_to(np.array(canonical[method]), (len(weights), reference['n_random'], k))
                    else:
                        chosen = weighted_choices(pool, dw, k, method)
                        uniform_choice_mismatches += int(not np.array_equal(chosen[0], canonical[method][0]))
                        if uniform_choice_mismatches:
                            raise ValueError(f'Uniform selection differs: {key}, split {split_id}, k {k}, {method}')
                        choices = chosen[:, None, :]
                    for bi, baseline in enumerate((None, bare)):
                        score = weighted_evaluate(pool, choices, dw, tw, baseline)
                        np.testing.assert_allclose(score[0], evaluate(pool, canonical[method], dev, heldout, baseline), atol=1e-12)
                        totals[:, ki, mi, bi] += score
        print(f'split {split_id+1}/{len(reference["split_manifest"])} complete', flush=True)
    totals /= len(keys)*len(reference['split_manifest'])
    return totals, schedule_hash.hexdigest(), uniform_choice_mismatches


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--draws', type=int, default=199)
    ap.add_argument('--seed', type=int, default=20260910)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        raise FileExistsError('Use a new output file; do not overwrite a completed sensitivity run')
    groups, inventory, audit = load_sources({'AD': P2/'primary_input_manifest.json', 'BC': P2/'bc_input_manifest.json'})
    mem, gen_inventory, _ = membership()
    split_path = ROOT/'experiment/phase2/split_p2_test_core.json'
    tasks = task_ids(split_path)
    records, cells, _ = candidate_records(groups, mem, tasks)
    pools = {key: np.array([[records[h, t]['official_correct'] for t in tasks] for h in names], dtype=float)
             for key, names in cells.items()}
    keys = sorted(cells, key=lambda key: tuple(cells[key][0].split('_')[2:4]))
    ref_path = ROOT/'artifacts/revision_20260910/selection.json'
    ref = json.loads(ref_path.read_text(encoding='utf-8'))
    frozen_inputs = inventory+gen_inventory+[{'path': str(p.relative_to(ROOT)).replace('\\', '/'), 'sha256': digest(p)} for p in
        (split_path, ref_path, ROOT/'experiment/revision/selection.py', ROOT/'experiment/revision/fingerprint.py', ROOT/'experiment/revision/replay.py', Path(__file__))]
    for item in ref['inputs'] + frozen_inputs:
        if digest(ROOT/item['path']) != item['sha256']:
            raise ValueError('Source differs from recorded canonical input: '+item['path'])
    weights = np.vstack([np.ones(len(tasks)), positive_weights([t.rpartition('#')[0] for t in tasks], args.draws, args.seed)])
    values, schedule_hash, mismatches = analyze(pools, keys, vector(groups['AD'], 'bare', tasks), tasks, ref, weights)
    summary = {}
    for ki, k in enumerate((4, 8)):
        for mi, method in enumerate(METHODS):
            for bi, baseline in enumerate(('candidate_only', 'bare_inclusive')):
                np.testing.assert_allclose(values[0, ki, mi, bi], ref['summary'][f'{method}|k={k}'][baseline], atol=1e-12)
                delta = values[1:, ki, mi, bi] - values[1:, ki, 0, bi]
                summary[f'{method}|k={k}|{baseline}'] = {'reference_mean': values[0, ki, mi, bi].tolist(),
                    'paired_difference_perturbation_quantiles_025_50_975': np.quantile(delta, [.025, .5, .975], axis=0).T.tolist()}
    sidecar = args.out.with_suffix('.npz')
    if sidecar.exists():
        raise FileExistsError(sidecar)
    for item in ref['inputs'] + frozen_inputs:
        if digest(ROOT/item['path']) != item['sha256']:
            raise ValueError('Input changed during weighted analysis: '+item['path'])
    np.savez_compressed(sidecar, weights=weights, values=values)
    result = {'version': 'w1-joint-positive-weight-development-v1',
        'scope': 'Joint re-selection sensitivity on fixed observed executions, 18 cells, 9 database identities, original 100 splits and random subset draws; NOT confidence intervals or independent utility evidence',
        'draws': args.draws, 'seed': args.seed, 'metric_order': METRICS,
        'array_axes': ['uniform_then_weight_draw', 'k4_k8', 'method', 'candidate_only_bare_inclusive', 'metric'],
        'method_order': METHODS, 'cell_keys': keys, 'uniform_choice_mismatches': mismatches,
        'uniform_row_policy': 'Same weighted kernel; any mismatch with canonical choices aborts the run.',
        'sampling': 'Independent Exp(1) database weights times within-database Exp(1) task weights normalized to original database task count; same vector shared across every comparison. Fixed builders and seeds, no new execution variation.',
        'discrete_bootstrap_empty_side': empty_side_probability(ref['split_manifest']),
        'random_schedule_sha256': schedule_hash, 'summary': summary, 'canonical_source_audit': audit,
        'inputs': frozen_inputs, 'canonical_reference_input_bindings': ref['inputs'],
        'sidecar': {'path': str(sidecar), 'sha256': digest(sidecar)}}
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
