"""Offline calibration of re-selection bootstrap; no formal-design clearance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from experiment.revision.replay import ROOT, digest
from experiment.revision.repeat_planning import (
    build_populations, cross_repeat, generate_execution, logits,
    marginal_probabilities, sigmoid, tied_max_weights,
)

SCENARIOS = {
    "database_null": dict(interaction=0., db_sd=1., execution_sd=.8, block_sd=0., cache=0.),
    "database_interaction": dict(interaction=.8, db_sd=1., execution_sd=.8, block_sd=0., cache=0.),
    "database_and_time": dict(interaction=.8, db_sd=1., execution_sd=.8, block_sd=1.2, cache=0.),
    "cache_null": dict(interaction=0., db_sd=1., execution_sd=.8, block_sd=0., cache=.9),
}


def simulated_panel(rng, n_databases, tasks_per_database, repeats, settings, concentration, anchor_codes=None):
    """Four fixed population slots; development acquisition independent of eval.

    Base simulator supplies paired clone identities and a dev-selected code.
    Evaluation tasks additionally share database difficulty and random
    member-by-database execution shocks. They do not reuse development tasks.
    """
    count = n_databases * tasks_per_database
    base_settings = dict(strength=0., interaction=settings['interaction'])
    p, codes = build_populations(rng, count, 4, base_settings, .64, concentration)
    if anchor_codes is not None:
        for cell, anchor in enumerate(anchor_codes):
            p[cell, 2, 0] = p[cell, 0, 0]
            p[cell, 2, 1:] = p[cell, 0, anchor]
            codes[cell, 2] = [0, anchor, anchor]
    db_ids = np.repeat(np.arange(n_databases), tasks_per_database)
    database_shift = rng.normal(0, settings['db_sd'], n_databases)
    p = sigmoid(logits(p) + database_shift[db_ids])
    # Draw fresh grouped noise before the optional cache overlay. Unlike a code
    # parameter, a request/time shock is independently drawn for clone executions.
    time_shift = rng.normal(0, settings['block_sd'], repeats)
    db_shock = rng.normal(0, settings['execution_sd'], (4, 3, repeats, 3, n_databases))
    q = sigmoid(logits(p)[:, :, None] + time_shift[None, None, :, None, None]
                + db_shock[..., db_ids])
    fresh = (rng.random(q.shape) < q).astype(float)
    if settings['cache']:
        # generate_execution provides an explicit code-keyed cached panel.
        # Use its fully cached counterpart, not an independently keyed mask per task draw.
        cached, _ = generate_execution(rng, p, codes, repeats, 0., 1.)
        use = rng.random(fresh.shape) < settings['cache']
        y = np.where(use, cached, fresh)
    else:
        y = fresh
    # Independent future execution averages over both normal shock sources.
    marginal = marginal_probabilities(p, np.hypot(settings['block_sd'], settings['execution_sd']))
    truth = np.broadcast_to(marginal[:, :, None], y.shape)
    observed, oracle = cross_repeat(y, truth)
    return y, db_ids, float(np.mean(observed[:, 0, 0] - observed[:, 2, 0])), float(
        np.mean(oracle[:, 0, 0] - oracle[:, 2, 0]))


def resampling_weights(rng, db_ids, repeats, n_boot, hierarchical=True):
    """Global paired task draws and separate original-repeat support per half."""
    if repeats < 2 or repeats % 2:
        raise ValueError('even repeat count >=2 required')
    databases = np.unique(db_ids)
    groups = [np.flatnonzero(db_ids == d) for d in databases]
    if len({len(g) for g in groups}) != 1:
        raise ValueError('this planning calibration uses equal-size database clusters')
    n = len(db_ids)
    task_weights = np.zeros((n_boot, n))
    for b in range(n_boot):
        if hierarchical:
            chosen = rng.integers(len(groups), size=len(groups))
            indices = np.concatenate([rng.choice(groups[d], len(groups[d]), replace=True) for d in chosen])
        else:
            indices = rng.integers(n, size=n)
        task_weights[b] = np.bincount(indices, minlength=n) / n
    half = repeats // 2
    repeat_weights = np.zeros((n_boot, 2, repeats))
    for side in range(2):
        draws = rng.integers(half, size=(n_boot, half)) + side * half
        for b in range(n_boot):
            repeat_weights[b, side] = np.bincount(draws[b], minlength=repeats) / half
    return task_weights, repeat_weights


def bootstrap_scores(outcomes, task_weights, repeat_weights):
    """Re-fit per-task and global fixed choices for each paired bootstrap draw.

    Shape: outcomes[cell,group,repeat,member,task]. Repeat weights use
    disjoint original records in the two halves; sharing draws preserves pairing.
    """
    halves = [np.einsum('br,cgrht->bcght', repeat_weights[:, side], outcomes)
              for side in range(2)]
    scores = []
    for side in range(2):
        train, validation = halves[side], halves[1-side]
        per_task = tied_max_weights(train, axis=3)
        fixed = tied_max_weights(np.einsum('bcght,bt->bcgh', train, task_weights), axis=3)
        chosen = np.einsum('bcght,bcght,bt->bcg', per_task, validation, task_weights)
        comparator = np.einsum('bcgh,bcght,bt->bcg', fixed, validation, task_weights)
        advantage = chosen - comparator
        scores.append((advantage[:, :, 0] - advantage[:, :, 2]).mean(axis=1))
    return (scores[0] + scores[1]) / 2


def interval_calibration(estimates, intervals, target, target_mc_se):
    lo, hi = intervals.T
    lower_target, upper_target = target - 1.96*target_mc_se, target + 1.96*target_mc_se
    coverage = (lo <= target) & (hi >= target)
    return dict(target=target, target_reference_mc_se=target_mc_se,
        bias=float(estimates.mean()-target), mean_estimate=float(estimates.mean()),
        coverage=float(coverage.mean()), coverage_mc_se=float(np.sqrt(coverage.mean()*(1-coverage.mean())/len(lo))),
        coverage_reference_band_lower=float(np.mean((lo <= lower_target) & (hi >= upper_target))),
        coverage_reference_band_upper=float(np.mean((lo <= upper_target) & (hi >= lower_target))),
        mean_width=float(np.mean(hi-lo)), median_width=float(np.median(hi-lo)),
        positive_interval_fraction=float(np.mean(lo > 0)), negative_interval_fraction=float(np.mean(hi < 0)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--n-sim', type=int, default=300)
    parser.add_argument('--n-reference', type=int, default=3000)
    parser.add_argument('--n-boot', type=int, default=399)
    parser.add_argument('--seed', type=int, default=20260911)
    args = parser.parse_args()
    if min(args.n_sim, args.n_reference, args.n_boot) < 100:
        parser.error('at least 100 simulations, reference draws and bootstrap draws')
    out = ROOT/'artifacts/revision_20260910'
    sensitivity = json.loads((out/'sensitivity.json').read_text(encoding='utf-8'))
    flip = sensitivity['r2']['micro_verdict_flips']['rate']
    concentration = flip/(2*.64*.36-flip)
    sequences = np.random.SeedSequence(args.seed).spawn(8)
    results = []
    for index, (name, settings) in enumerate(SCENARIOS.items()):
        for design_index, (databases, per_db, repeats) in enumerate([(9, 20, 4), (9, 40, 8)]):
            anchor_rng, reference_rng, data_rng, bootstrap_rng = [np.random.default_rng(s) for s in sequences[index*2+design_index].spawn(4)]
            _, anchor_identity = build_populations(anchor_rng, 1, 4,
                dict(strength=0., interaction=settings['interaction']), .64, concentration)
            anchors = anchor_identity[:, 2, 1]
            reference = np.array([simulated_panel(reference_rng, databases, per_db, repeats, settings, concentration, anchors)[3]
                                  for _ in range(args.n_reference)])
            target = float(reference.mean())
            target_se = float(reference.std(ddof=1)/np.sqrt(args.n_reference))
            if settings['interaction'] == 0:
                # All codes have identical marginal task probabilities: exact fresh target zero.
                assert np.max(np.abs(reference)) < 1e-12
                target, target_se = 0., 0.
            estimates, intervals = [], {'database_task_repeat': [], 'iid_task_repeat': []}
            for _ in range(args.n_sim):
                y, ids, observed, _ = simulated_panel(data_rng, databases, per_db, repeats, settings, concentration, anchors)
                estimates.append(observed)
                for method in intervals:
                    weights = resampling_weights(bootstrap_rng, ids, repeats, args.n_boot, method.startswith('database'))
                    values = bootstrap_scores(y, *weights)
                    intervals[method].append(np.quantile(values, [.025, .975]))
            row = dict(scenario=name, settings=settings, n_databases=databases, n_tasks=databases*per_db,
                n_repeats=repeats, frozen_dev_selected_anchor_codes=anchors.tolist(), reference_mean=target, reference_mc_se=target_se,
                methods={method: interval_calibration(np.array(estimates), np.array(bounds), target, target_se)
                         for method, bounds in intervals.items()})
            results.append(row)
            print(name, row['n_tasks'], repeats, row['methods'], flush=True)
    paths = [Path(__file__), ROOT/'experiment/revision/repeat_planning.py',
             ROOT/'experiment/revision/replay.py', out/'sensitivity.json']
    report = dict(version='repeat-inference-development-v1', seed=args.seed, n_sim=args.n_sim,
        n_reference=args.n_reference, n_boot=args.n_boot,
        estimand='expected fresh-execution advantage of the finite-repeat fitted policy, real minus dev-selected-code clone; equal database sizes; four fixed population slots; conditional on one independently development-selected anchor per cell, averaged over simulated task sets and discovery executions',
        purpose='calibrate a candidate percentile re-selection bootstrap; not a validated formal estimator, not empirical paper results or a budget/sample-size freeze',
        assumptions=['synthetic nine-database population, 20 or40 tasks per database,4 or8 repeats; different from initial200/400-task grid',
            'database logit sd1, independent member/database/repeat execution shock sd.8; optional shared time logit sd1.2',
            'fixed four population slots; builder and new-generation population uncertainty not represented',
            'anchor code is selected on a separate200-task development sample once per scenario/design and frozen for reference and calibration draws',
            'reference draws independent of calibration draws and bootstrap RNG; alternative truth is Monte Carlo with reported uncertainty',
            'both methods re-fit per-task and fixed members; task weights shared across all cells/groups; repeat weights global and restricted to each original half',
            'same task may repeat in a bootstrap draw; no original raw execution appears in both halves of a directional comparison',
            'cache stress violates independent validation, and intervals are not expected to fix that bias',
            'equal member counts do not imply equal compute; development population uses preceding simulator settings, not fitted real data'],
        calibration=dict(mean_accuracy_assumption=.64, beta_concentration=concentration, flip_input=flip),
        results=results, inputs=[dict(path=p.relative_to(ROOT).as_posix(), sha256=digest(p)) for p in paths])
    (out/'repeat_inference.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
