"""Canonical descriptive W1 replay; held-out task scores, no selection-gain claim.

Retains legacy seed, split/draw counts and candidate selection rules, with a
new deterministic recorded schedule. Reports two baseline estimands separately.
No legacy cell-only confidence intervals are carried into this result.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np

from experiment.revision.fingerprint import candidate_records
from experiment.revision.replay import P2, ROOT, digest, load_sources, membership, task_ids, vector
from experiment.revision.sensitivity import OUT

METHODS = ['top-acc', 'random', 'div-only', 'acc+0.25div', 'acc+0.5div', 'acc+1.0div', 'acc+2.0div']
METRICS = ['oracle_accuracy', 'best_fixed', 'headroom', 'dev_selected_fixed_accuracy']


def selections(pool, k, dev, rng, n_random=200):
    """Names are sorted upstream; preserve legacy ascending/descending tie rules."""
    if not 1 <= k <= len(pool):
        raise ValueError('insufficient admitted population for requested k')
    accs = pool[:, dev].mean(axis=1)
    results = {'top-acc': [sorted(range(len(pool)), key=lambda i: (-accs[i], i))[:k]],
               'random': [rng.sample(range(len(pool)), k) for _ in range(n_random)]}
    for name in METHODS[2:]:
        lam = None if name == 'div-only' else float(name[4:-3])
        chosen = [max(range(len(pool)), key=lambda i: (accs[i], i))]
        while len(chosen) < k:
            def score(i):
                candidate = chosen + [i]
                oracle = pool[candidate][:, dev].max(axis=0).mean()
                return (oracle if lam is None else accs[candidate].mean() + lam * oracle, i)
            chosen.append(max((i for i in range(len(pool)) if i not in chosen), key=score))
        results[name] = [chosen]
    return results


def evaluate(pool, subsets, dev, heldout, bare=None):
    """Evaluate held-out oracle/best separately from a dev-only fixed choice."""
    # Canonical member-name order (pool rows are sorted upstream) makes dev-fixed
    # ties independent of the order in which a method selected those members.
    values = pool[np.sort(np.array(subsets), axis=1)]
    if bare is not None:
        values = np.concatenate([np.broadcast_to(bare, (len(subsets), 1, len(bare))), values], axis=1)
    test_acc = values[:, :, heldout].mean(axis=2)
    oracle = values[:, :, heldout].max(axis=1).mean(axis=1)
    best = test_acc.max(axis=1)
    dev_winner = values[:, :, dev].mean(axis=2).argmax(axis=1)
    selected = test_acc[np.arange(len(subsets)), dev_winner]
    return np.array([oracle.mean(), best.mean(), (oracle-best).mean(), selected.mean()])


def analyze(groups, mem, tasks, n_splits=100, n_random=200):
    records, cells, arms = candidate_records(groups, mem, tasks)
    bare = vector(groups['AD'], 'bare', tasks)
    dbs = sorted({t.rpartition('#')[0] for t in tasks})
    pools = {key: np.array([[records[h, t]['official_correct'] for t in tasks] for h in names], dtype=float)
             for key, names in cells.items()}
    # New deterministic order. Legacy set-derived cell order was not archived;
    # shared RNG use means its historical splits/draws cannot be reconstructed exactly.
    keys = sorted(cells, key=lambda key: tuple(cells[key][0].split('_')[2:4]))
    rng = random.Random(20260908)
    results, split_manifest = [], []
    for split_id in range(n_splits):
        shuffled = dbs[:]
        rng.shuffle(shuffled)
        dev_dbs = set(shuffled[:len(shuffled)//2])
        dev = np.array([i for i,t in enumerate(tasks) if t.rpartition('#')[0] in dev_dbs])
        heldout = np.array([i for i,t in enumerate(tasks) if t.rpartition('#')[0] not in dev_dbs])
        if not len(dev) or not len(heldout):
            raise ValueError('database split must have both dev and held-out tasks')
        split_manifest.append(dict(split_id=split_id, dev_databases=sorted(dev_dbs),
                                   heldout_databases=sorted(set(dbs)-dev_dbs)))
        for key in keys:
            pool = pools[key]
            for k in (4, 8):
                selected = selections(pool, k, dev, rng, n_random)
                for name in METHODS:
                    results.append(dict(builder=key[0], seed=key[1], split_id=split_id, k_candidate=k,
                        method=name, candidate_only=evaluate(pool, selected[name], dev, heldout).tolist(),
                        bare_inclusive=evaluate(pool, selected[name], dev, heldout, bare).tolist()))
    summary = {}
    for k in (4,8):
        for name in METHODS:
            rows = [r for r in results if r['k_candidate'] == k and r['method'] == name]
            summary[f'{name}|k={k}'] = {scope: np.mean([r[scope] for r in rows],axis=0).tolist()
                                      for scope in ('candidate_only', 'bare_inclusive')}
    return dict(n_cells=len(cells), n_harnesses=len(arms), n_tasks=len(tasks), n_splits=n_splits,
        n_random=n_random, metric_order=METRICS, summary=summary, split_manifest=split_manifest,
        per_cell_split=results)


def main():
    groups, inventory, audit = load_sources({'AD': P2/'primary_input_manifest.json',
                                           'BC': P2/'bc_input_manifest.json'})
    mem, gen_inventory, _ = membership()
    split = ROOT/'experiment/phase2/split_p2_test_core.json'
    result = analyze(groups, mem, task_ids(split))
    result.update(analysis_version='selection-20260910-v1',
        scope='post-hoc descriptive replay; fixed observed executions, no confidence intervals or independent transfer claim',
        weighting='equal mean over 18 cells and 100 overlapping database splits; neither 1800 independent observations nor new independent evaluation',
        bare_policy='same AD bare always added after candidate selection for bare_inclusive evaluation; candidate k excludes bare',
        ties='candidate selection: top-acc ascending name; greedy descending name; dev-fixed: ascending member name within selected subset, bare first when included',
        schedule='new deterministic schedule with legacy seed/counts/rules; historical set-derived cell order was not archived, so historical random draws are not exactly recoverable',
        dev_fixed_limit='all deterministic methods contain a globally dev-best candidate; differences may reflect which tied maxima are retained, not improved maximum dev accuracy',
        canonical_source_audit=audit)
    result['inputs'] = inventory + gen_inventory + [
        dict(path=p.relative_to(ROOT).as_posix(), sha256=digest(p)) for p in
        (split, ROOT/'experiment/revision/replay.py', ROOT/'experiment/revision/fingerprint.py',
         ROOT/'experiment/revision/sensitivity.py', Path(__file__))]
    (OUT/'selection.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n',encoding='utf-8')
    for scope in ('candidate_only','bare_inclusive'):
        print(scope, 'div-only minus top-acc k8',
              np.array(result['summary']['div-only|k=8'][scope])-result['summary']['top-acc|k=8'][scope])


if __name__ == '__main__':
    main()
