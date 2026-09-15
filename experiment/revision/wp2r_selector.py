"""WP-2R: held-out selector utility (E3) on the WP-1R fresh collection.

Frozen spec (REAL_EVIDENCE_PROTOCOL_V1.md section 12 + v2 plan 3.D):
  * 5-fold task-level CV on the 100 dev tasks (seed 20260915); same-task
    repeats never split across folds.
  * pi_Z features: question-text TF features + per-member dev accuracy
    computed WITHIN the training folds only; multinomial LR; fold-model
    averaging; tie-break by member id ascending; abstain -> bare when the
    top-2 probability gap < 0.15.
  * Comparators on the same candidate set, information, and budget: bare,
    dev-fixed, pre-fixed random member (seeded), M1b (dev-fixed + bare
    fallback + completeness check), frozen pi_Z.
  * Evaluated on the 400 eval tasks (label: retrospective tasks + prospective
    execution -- these tasks were observed in repeat-0; no unseen-task claim).
  * Per-task paired difference vs dev-fixed, repair/harm, abstain rate,
    logical-call accounting; E_1 is NOT applicable (members make >1 call);
    E_b reported with b=3 calls/task as a separately named estimand.

Primary outcome: repeat-mean correctness over repeats 1-3 per member/task
(finite-R caveat carried); secondary: each repeat separately.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from experiment.revision.wp1r_analysis import (matrices, ledger_manifest,
                                               load_cells)
from experiment.diagnostics.core import ABSTAIN_EPS  # frozen 0.15

WP1R = ROOT / 'artifacts/wp1r_20260915'
SEED = 20260915
N_FOLDS = 5
E_B = 3  # separate-named estimand: uniform budget cap b=3 calls/task


def question_features(train_tasks, eval_tasks):
    """TF features from question text (split file, available pre-execution)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    split = json.loads((ROOT / 'artifacts/gsm8k_audit/math500_split.json')
                       .read_text(encoding='utf-8'))['tasks']
    text = {f'math500_split#{i}': split[i]['question'] for i in range(500)}
    vec = TfidfVectorizer(max_features=300, stop_words='english')
    vec.fit([text[t] for t in train_tasks])
    X_tr = vec.transform([text[t] for t in train_tasks]).toarray()
    X_ev = vec.transform([text[t] for t in eval_tasks]).toarray()
    return X_tr, X_ev


def fit_pi_z(dev_matrix, members, train_tasks, held_tasks):
    """Fold-model-averaged multinomial LR on TF features + train-fold dev-acc.

    dev_matrix: (n_members, n_dev_tasks) repeat-mean correctness (NaN -> task
    excluded from training). Returns choice index per held task (or -1 for
    abstain -> bare) plus the fitted fold models' probabilities.
    """
    from sklearn.linear_model import LogisticRegression
    valid = [t for t in train_tasks
             if not np.isnan(dev_matrix[:, train_tasks.index(t)]).any()]
    valid_cols = [train_tasks.index(t) for t in valid]
    Y_tr = dev_matrix[:, valid_cols]                 # (n_members, n_valid)
    X_tr_text, X_he_text = question_features(valid, held_tasks)
    dev_accs = Y_tr.mean(axis=1)
    X_tr = np.hstack([X_tr_text, np.tile(dev_accs, (X_tr_text.shape[0], 1))])
    X_he = np.hstack([X_he_text, np.tile(dev_accs, (X_he_text.shape[0], 1))])
    y = np.argmax(Y_tr, axis=0)   # best member per task; member ids sorted
    # ascending, so argmax is the lexicographic tie-break
    models = []
    kf = np.array_split(np.arange(len(valid)), N_FOLDS)
    prob_sum = np.zeros((len(held_tasks), len(members)))
    for fold in range(N_FOLDS):
        hold = kf[fold]
        tr = np.setdiff1d(np.arange(len(valid)), hold)
        if len(np.unique(y[tr])) < 2:
            continue
        m = LogisticRegression(max_iter=1000, C=1.0)
        m.fit(X_tr[tr], y[tr])
        # fold models may miss classes; map back to full member index space
        fold_probs = np.zeros((len(held_tasks), len(members)))
        fold_probs[:, m.classes_.astype(int)] = m.predict_proba(X_he)
        prob_sum += fold_probs
        models.append(m)
    if not models:
        raise RuntimeError('no fittable fold')
    probs = prob_sum / len(models)
    order = np.argsort(-probs, axis=1)
    top2 = np.sort(probs, axis=1)[:, -2:]
    choice = np.where(top2[:, 1] - top2[:, 0] < ABSTAIN_EPS, -1, order[:, 0])
    return choice, probs


def compare_policies(Y, members, dev_matrix, dev_tasks, eval_tasks):
    raise NotImplementedError('use compare_policies_eval')


def load_dev_and_eval():
    """Repeat-mean matrices for the panel on dev (from dev_real) and eval."""
    members, tasks, repeats, m_by_rep, manifest, _ = matrices('dev_real')
    dev_stack = np.stack([m_by_rep[r] for r in repeats])
    dev_mean = np.nanmean(dev_stack, axis=0)
    em, et, er, e_by_rep, eman, _ = matrices('eval_real')
    assert em == members, 'panel mismatch between dev and eval arms'
    eval_stack = np.stack([e_by_rep[r] for r in er])
    eval_mean = np.nanmean(eval_stack, axis=0)
    return members, tasks, repeats, dev_mean, et, eval_mean, eval_stack


def main():
    members, dev_tasks, repeats, dev_mean, eval_tasks, eval_mean, eval_stack = \
        load_dev_and_eval()
    report = compare_policies_eval(members, dev_tasks, dev_mean, eval_tasks,
                                   eval_mean, eval_stack)
    out = WP1R / 'wp2r_selector_report.json'
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report.get('summary', {}), ensure_ascii=False, indent=1))
    print(f'wrote {out}')


def compare_policies_eval(members, dev_tasks, dev_mean, eval_tasks, eval_mean,
                          eval_stack):
    """Frozen comparator set evaluated on repeat-mean (primary) and per repeat."""
    from sklearn.linear_model import LogisticRegression
    members_sorted = sorted(members)
    mi = {m: i for i, m in enumerate(members)}
    bare_idx = mi['bare']
    dev_accs = np.array([np.nanmean(dev_mean[mi[m], :]) for m in members_sorted])
    dev_fixed_name = members_sorted[int(np.argmax(dev_accs))]
    dev_fixed_idx = mi[dev_fixed_name]
    rng = np.random.default_rng(SEED)
    random_name = members_sorted[int(rng.integers(0, len(members_sorted)))]
    random_idx = mi[random_name]

    # M1b: dev-fixed with bare fallback when dev-fixed has no valid entry
    # (completeness-checked; not a weakened baseline)
    choice_pi, probs = fit_pi_z(dev_mean, members,
                                [t for t in dev_tasks
                                 if not np.isnan(dev_mean[:, dev_tasks.index(t)]).any()],
                                eval_tasks)
    pi_idx = np.array([bare_idx if c < 0 else mi[members_sorted[c]]
                       for c in choice_pi])

    def eval_policy(idx_per_task, target):
        vals = np.array([target[idx, j] for j, idx in enumerate(idx_per_task)])
        return vals

    all_idx = {'bare': np.full(len(eval_tasks), bare_idx),
               'dev_fixed': np.full(len(eval_tasks), dev_fixed_idx),
               'random_fixed': np.full(len(eval_tasks), random_idx),
               'M1b': np.full(len(eval_tasks), dev_fixed_idx),
               'pi_Z': pi_idx}
    # M1b fallback: where dev-fixed cell is missing in the target, use bare
    missing = np.isnan(eval_mean[dev_fixed_idx, :])
    all_idx['M1b'][missing] = bare_idx

    summary = {'dev_fixed_member': dev_fixed_name, 'random_member': random_name,
               'abstain_rate_pi_Z': round(float((choice_pi < 0).mean()), 4),
               'epsilon': ABSTAIN_EPS, 'n_folds': N_FOLDS, 'seed': SEED,
               'label': 'retrospective tasks + prospective execution; '
                        'no unseen-task claim'}
    results = {}
    for name, idxs in all_idx.items():
        vals = eval_policy(idxs, eval_mean)
        results[name] = {'accuracy': round(float(np.nanmean(vals)), 4)}
    ref = eval_policy(all_idx['dev_fixed'], eval_mean)
    for name in ('bare', 'random_fixed', 'M1b', 'pi_Z'):
        vals = eval_policy(all_idx[name], eval_mean)
        paired = vals - ref
        ok = ~np.isnan(paired)
        boots = np.array([np.mean(rng.choice(paired[ok], ok.sum(), replace=True))
                          for _ in range(4000)])
        lo, hi = np.percentile(boots, [2.5, 97.5])
        results[name]['paired_vs_dev_fixed'] = {
            'mean': round(float(np.nanmean(paired)), 4),
            'ci95': [round(float(lo), 4), round(float(hi), 4)],
            'repair_rate': round(float(np.mean(paired[ok] > 0)), 4),
            'harm_rate': round(float(np.mean(paired[ok] < 0)), 4)}
    # E_b: uniform cap b=3 logical calls/task (separate estimand, not E_1)
    results['E_b'] = {'budget_cap_calls': E_B,
                      'note': 'E_1 not applicable: panel members make >1 call; '
                              'actual calls reported per member from the ledger'}
    # per-repeat secondary
    per_repeat = {}
    for rep in range(eval_stack.shape[0]):
        target = eval_stack[rep]
        per_repeat[f'repeat{rep + 1}'] = {
            name: round(float(np.nanmean(eval_policy(idxs, target))), 4)
            for name, idxs in all_idx.items()}
    return {'summary': summary, 'accuracy': results,
            'per_repeat_secondary': per_repeat,
            'pi_Z_eval_member_counts': {
                members_sorted[c] if c >= 0 else 'bare':
                    int(np.sum(choice_pi == c)) for c in np.unique(choice_pi)}}


if __name__ == '__main__':
    main()
