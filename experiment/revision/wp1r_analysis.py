"""WP-1R/WP-2R analysis: E1/E2 (C-rank / C-comp), A8.6 clone-null test, E4 accounting.

Reads the fresh-acquisition RunStore ledgers (eval_real, eval_clone, dev_real)
written by experiment/revision/fresh_collect_math.py and produces the frozen
analysis report (REAL_EVIDENCE_PROTOCOL_V1.md A5/A8.6):

  * E1 (C-rank) and E2 (C-comp) states come from the reviewed diagnostics
    machinery (experiment.diagnostics.core.s3_stability) fed with one
    Population per fresh repeat (same frozen condition fields).
  * A8.6 primary test: discovery (repeat 1) -> frozen per-task mapping ->
    validation (repeats 2-3) task-conditional advantage vs bare for the real
    panel; the same procedure on the 9 same-code clone slots (baseline
    clone-c1); one-sided permutation p over joint cross-repeat identity
    permutations within tasks; task-level bootstrap CI of D = A_real - A_clone.
  * E4: accounting rollup (logical calls, attempts, tokens, conservative
    cost ceiling at the frozen break-even price).

Missing cells stay NaN (never imputed) for the s3 machinery; the A8.6
complete-case rule drops tasks with any missing member/repeat and reports
the exclusion list and coverage.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from experiment.diagnostics.core import Population, s3_stability  # noqa: E402

WP1R = ROOT / 'artifacts/wp1r_20260915'
BREAK_EVEN_PRICE_PER_M = 44.3   # frozen budget-gate v1.3 (CNY per 1M tokens)
SEED = 20260915
N_PERM = 10000
N_BOOT = 10000
DELTA = 0.01                    # 1.0 pp, frozen


def load_cells(ledger: Path):
    """Yield cell dicts from a fresh_collect_math RunStore ledger."""
    conn = sqlite3.connect(f'file:{ledger}?mode=ro', uri=True)
    rows = conn.execute(
        "SELECT result FROM tasks WHERE result IS NOT NULL").fetchall()
    for (v,) in rows:
        yield json.loads(v)


def collect_events(ledger: Path):
    conn = sqlite3.connect(f'file:{ledger}?mode=ro', uri=True)
    for (v,) in conn.execute("SELECT value FROM events ORDER BY id"):
        yield json.loads(v)


def ledger_manifest(ledger: Path):
    conn = sqlite3.connect(f'file:{ledger}?mode=ro', uri=True)
    row = conn.execute("SELECT value FROM manifest WHERE id=1").fetchone()
    return json.loads(row[0])


def matrices(config_name: str):
    """member/slot x task matrices per repeat from one arm's ledger."""
    ledger = WP1R / config_name / 'ledger.sqlite'
    cells = list(load_cells(ledger))
    manifest = ledger_manifest(ledger)
    members = sorted({c['harness'] for c in cells})
    tasks = sorted({c['task'] for c in cells})
    repeats = sorted({c['repeat'] for c in cells})
    m_idx = {m: i for i, m in enumerate(members)}
    t_idx = {t: j for j, t in enumerate(tasks)}
    out = {}
    for rep in repeats:
        Y = np.full((len(members), len(tasks)), np.nan)
        for c in cells:
            if c['repeat'] == rep and c.get('official_correct') is not None:
                Y[m_idx[c['harness']], t_idx[c['task']]] = c['official_correct']
        out[rep] = Y
    return members, tasks, repeats, out, manifest, cells


def build_populations(members, tasks, matrices_by_rep, manifest):
    """One Population per repeat with the frozen condition object."""
    cond = {
        'model': manifest['solver']['model'],
        'base_url': manifest['solver']['base_url'],
        'cache_mode': manifest['cache_mode'],
        'max_tokens': manifest['solver']['max_tokens'],
        'temperature_semantics': manifest['temperature_semantics'],
        'judge': manifest['judge'],
        'protocol': manifest['protocol'],
        'acquisition_id': manifest['acquisition_id'],
        'section': manifest['section'],
    }
    hashes = {h['id']: h['source_sha256_lf'] for h in manifest['harnesses']}
    pops = {}
    for rep, Y in matrices_by_rep.items():
        pops[f'repeat{rep}'] = Population(
            member_ids=list(members),
            source_hashes=[hashes[m] for m in members],
            tasks=list(tasks), Y=Y, condition=cond,
            has_bare='bare' in members)
    return pops


# --------------------------- A8.6 discovery/validation procedure -------------

def a86_statistic(Y, members, baseline, discovery_rep, validation_reps,
                  rng=None, permute=None):
    """Full A8.6 statistic on one arm's outcome tensor.

    Y: dict repeat -> (n_members, n_tasks) matrix.
    permute: optional per-task identity permutation (dict task_col -> array of
    member row indices) applied jointly across repeats before the procedure.
    Returns (A, adv_vector, task_mask) where A = mean adv over eligible tasks.
    """
    reps = sorted(Y)
    d_rep = discovery_rep
    v_reps = validation_reps
    n_m, n_t = Y[d_rep].shape
    base_idx = members.index(baseline)
    adv = []
    for j in range(n_t):
        col = {r: Y[r][:, j] for r in reps}
        if any(np.isnan(col[r]).any() for r in reps):
            continue  # complete-case rule
        if permute is not None:
            perm = permute[j]
            col = {r: col[r][perm] for r in reps}
        scores = col[d_rep]
        # member ids sorted ascending -> argmax picks first max (lexicographic)
        best = int(np.argmax(scores))
        adv.append(np.mean([col[r][best] for r in v_reps])
                   - np.mean([col[r][base_idx] for r in v_reps]))
    adv = np.asarray(adv, dtype=float)
    A = float(np.mean(adv)) if adv.size else float('nan')
    return A, adv


def joint_permutations(n_members, n_tasks, rng):
    """Per-task identity permutations applied jointly across repeats."""
    return [rng.permutation(n_members) for _ in range(n_tasks)]


def a86_test(real_Y, real_members, clone_Y, clone_members):
    """Frozen A8.6 primary test. Returns the full result dict."""
    rng = np.random.default_rng(SEED)
    d_rep, v_reps = 1, (2, 3)
    A_real, adv_real = a86_statistic(real_Y, real_members, 'bare', d_rep,
                                     v_reps)
    A_clone, adv_clone = a86_statistic(clone_Y, clone_members, 'clone-c1',
                                       d_rep, v_reps)
    D = A_real - A_clone
    n_t = min(len(adv_real), len(adv_clone))
    # permutation null within clone slots (exchangeable identical code)
    n_m = len(clone_members)
    null = np.empty(N_PERM)
    for b in range(N_PERM):
        perm = joint_permutations(n_m, clone_Y[d_rep].shape[1], rng)
        A_perm, _ = a86_statistic(clone_Y, clone_members, 'clone-c1', d_rep,
                                  v_reps, permute=perm)
        null[b] = A_perm
    p = (1 + int(np.sum(null >= A_real - DELTA))) / (N_PERM + 1)
    # task-level bootstrap of D
    boots = np.empty(N_BOOT)
    brng = np.random.default_rng(SEED + 1)
    for b in range(N_BOOT):
        idx = brng.integers(0, n_t, n_t)
        boots[b] = np.mean(adv_real[idx]) - np.mean(adv_clone[idx])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    supported = bool(p < 0.05 and lo > 0 and A_real > DELTA)
    return {
        'estimand': 'A8.6 task-conditional advantage (discovery r1, validation r2-3)',
        'A_real': A_real, 'A_clone_obs': A_clone, 'D': D,
        'delta': DELTA, 'p_perm': p, 'D_ci95': [float(lo), float(hi)],
        'n_tasks_real': int(adv_real.size), 'n_tasks_clone': int(adv_clone.size),
        'state': 'SUPPORTED' if supported else
                 ('SUPPORTED_NOT_REACHED' if np.isfinite(A_real) else 'INSUFFICIENT'),
        'caveat': 'finite-R selection bias controlled only by the frozen '
                  'clone-null procedure; conclusions restricted to this panel, '
                  'condition, and task set',
    }


# --------------------------- E4 accounting ----------------------------------

def accounting(arm_names):
    out = {}
    total_tokens = total_attempts = total_calls = 0
    for name in arm_names:
        ledger = WP1R / name / 'ledger.sqlite'
        if not ledger.exists():
            continue
        attempts = calls = tokens = cells = 0
        for c in load_cells(ledger):
            acc = c.get('accounting', {})
            attempts += acc.get('http_attempts', 0)
            calls += acc.get('logical_calls', 0)
            t = acc.get('total_tokens')
            tokens += t if isinstance(t, int) else 0
            cells += 1
        out[name] = {'cells': cells, 'logical_calls': calls,
                     'http_attempts': attempts, 'known_total_tokens': tokens,
                     'conservative_cost_ceiling_cny': round(
                         tokens / 1e6 * BREAK_EVEN_PRICE_PER_M, 2)}
        total_tokens += tokens
        total_attempts += attempts
        total_calls += calls
    out['_total'] = {'logical_calls': total_calls, 'http_attempts': total_attempts,
                     'known_total_tokens': total_tokens,
                     'conservative_cost_ceiling_cny': round(
                         total_tokens / 1e6 * BREAK_EVEN_PRICE_PER_M, 2)}
    return out


def main():
    report = {}
    # E1/E2 on the real panel
    members, tasks, repeats, m_by_rep, manifest, _ = matrices('eval_real')
    pops = build_populations(members, tasks, m_by_rep, manifest)
    report['E1_C-rank_E2_C-comp'] = s3_stability(pops)
    report['panel'] = members
    report['n_tasks'] = len(tasks)
    report['repeats'] = repeats
    # A8.6 (requires eval_clone)
    if (WP1R / 'eval_clone' / 'ledger.sqlite').exists():
        cm, ct, cr, c_by_rep, cman, _ = matrices('eval_clone')
        c_pops = build_populations(cm, ct, c_by_rep, cman)
        report['clone_arm_s3'] = s3_stability(c_pops)
        report['E2_A86_clone_null'] = a86_test(m_by_rep, members, c_by_rep, cm)
    report['E4_accounting'] = accounting(['eval_real', 'eval_clone', 'dev_real', 'pilot'])
    out = WP1R / 'analysis_report.json'
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: report[k].get('state', 'n/a') if isinstance(report[k], dict)
                      else report[k] for k in report}, ensure_ascii=False))
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
