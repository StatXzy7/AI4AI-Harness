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
MAX_EXCLUDE_FRAC = 0.10         # A8.6 coverage gate, frozen


def load_cells(ledger: Path):
    """Yield cell dicts from a fresh_collect_math RunStore ledger."""
    conn = sqlite3.connect(f'file:{ledger}?mode=ro', uri=True)
    try:
        rows = conn.execute(
            "SELECT result FROM tasks WHERE result IS NOT NULL").fetchall()
    finally:
        conn.close()
    for (v,) in rows:
        yield json.loads(v)


def collect_events(ledger: Path):
    conn = sqlite3.connect(f'file:{ledger}?mode=ro', uri=True)
    try:
        rows = conn.execute("SELECT value FROM events ORDER BY id").fetchall()
    finally:
        conn.close()
    for (v,) in rows:
        yield json.loads(v)


def ledger_manifest(ledger: Path):
    conn = sqlite3.connect(f'file:{ledger}?mode=ro', uri=True)
    try:
        row = conn.execute("SELECT value FROM manifest WHERE id=1").fetchone()
    finally:
        conn.close()
    return json.loads(row[0])


# Continuation ledgers per arm, in chronological (precedence) order.  The
# 2026-09-17/18 stop-and-reconcile events split each arm's acquisition across
# ledgers that share the frozen solver condition; migrated rows are copies.
ARM_LEDGERS = {
    'eval_real': ['eval_real', 'eval_real_cont', 'eval_real_cont2'],
    'eval_clone': ['eval_clone', 'eval_clone_cont'],
    'dev_real': ['dev_real', 'dev_real_cont'],
}


def merge_cells(names):
    """Merge continuation ledgers into one cell map with a deterministic rule.

    Precedence per (harness, task, repeat) key: a completed observation
    (official_correct not None) beats an unknown_remote marker (None); among
    completed records the earliest ledger wins (first completed execution).
    Cells whose two completed records disagree are excluded from neither arm
    but recorded in the dedup report (first-completed retained).  Returns
    (cells_by_key, dedup_report).
    """
    merged = {}
    report = {'ledgers': list(names), 'rows_read': 0, 'unique_keys': 0,
              'identical_copies': 0, 'unknown_carried': 0,
              'completed_beats_unknown': 0, 'unknown_then_completed': 0,
              'both_completed_differ': [],
              'terminal_states': {}}
    for name in names:
        ledger = WP1R / name / 'ledger.sqlite'
        if not ledger.exists():
            continue
        for c in load_cells(ledger):
            report['rows_read'] += 1
            # terminal-state accounting: distinguish completed, unknown_remote,
            # and failed/error records rather than conflating all None outcomes
            if c.get('official_correct') is not None:
                state = 'completed'
            elif c.get('error') is not None:
                state = 'failed'
            else:
                state = c.get('outcome') or 'unknown_remote'
            report['terminal_states'][state] = \
                report['terminal_states'].get(state, 0) + 1
            key = (c['harness'], c['task'], c['repeat'])
            oc = c.get('official_correct')
            if key not in merged:
                merged[key] = c
                continue
            prev = merged[key]
            poc = prev.get('official_correct')
            if poc == oc:
                if poc is None:
                    report['unknown_carried'] += 1
                else:
                    report['identical_copies'] += 1
            elif poc is None:
                merged[key] = c  # completed beats unknown_remote
                report['unknown_then_completed'] += 1
            elif oc is None:
                report['completed_beats_unknown'] += 1
            else:
                report['both_completed_differ'].append({
                    'key': list(key), 'retained': poc, 'discarded': oc,
                    'retained_from': 'earlier ledger'})
    report['unique_keys'] = len(merged)
    return merged, report


def matrices(config_names, conflict_policy='first'):
    """member/slot x task matrices per repeat from one arm's ledger(s).

    Accepts a single ledger name or a list of continuation ledgers (merged
    with the deterministic precedence rule of merge_cells).
    conflict_policy: 'first' (frozen primary; retain earliest completed
    record for doubly-executed disagreeing cells) or 'nan' (frozen
    sensitivity; exclude those cells instead).
    Returns (members, tasks, repeats, matrices_by_repeat, manifest, cells, dedup).
    """
    if isinstance(config_names, str):
        config_names = [config_names]
    cell_map, dedup = merge_cells(config_names)
    if conflict_policy == 'nan':
        for rec in dedup['both_completed_differ']:
            h, t, r = rec['key']
            cell_map[(h, t, r)] = dict(cell_map[(h, t, r)],
                                       official_correct=None)
    cells = list(cell_map.values())
    existing = [n for n in config_names
                if (WP1R / n / 'ledger.sqlite').exists()]
    manifests = [ledger_manifest(WP1R / n / 'ledger.sqlite') for n in existing]
    manifest = dict(manifests[0])
    # integrity: continuation ledgers must share the frozen execution and
    # population identity fields (acquisition id, concurrency, budget and
    # protocol-amendment hashes legitimately differ across continuations)
    for field in ('solver', 'cache_mode', 'temperature_semantics', 'judge',
                  'protocol', 'section', 'repeats', 'harnesses', 'panel_draw',
                  'tasks_sha256', 'split_sha256', 'schedule_sha256',
                  'task_order'):
        for m in manifests[1:]:
            if m.get(field) != manifest.get(field):
                raise ValueError(
                    f'continuation manifest mismatch on {field}: '
                    f'{existing[0]} vs others')
    manifest['acquisition_id'] = [m['acquisition_id'] for m in manifests]
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
    return members, tasks, repeats, out, manifest, cells, dedup


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
        'section': manifest['section'],
        # acquisition_id is run IDENTITY (provenance), not an execution
        # condition: migrated continuation ledgers carry distinct run ids for
        # the same frozen condition, and the S3 identity gate must not read
        # them as condition drift.
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
    Returns (A, adv_vector, task_cols) where A = mean adv over eligible tasks
    and task_cols are the column indices of the complete-case tasks.
    """
    reps = sorted(Y)
    d_rep = discovery_rep
    v_reps = validation_reps
    n_m, n_t = Y[d_rep].shape
    base_idx = members.index(baseline)
    adv = []
    cols = []
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
        cols.append(j)
    adv = np.asarray(adv, dtype=float)
    A = float(np.mean(adv)) if adv.size else float('nan')
    return A, adv, cols


def impute_within_task(Y):
    """A8.6 sensitivity: fill a missing (member, task, repeat) cell with the
    member's mean over its available repeats on that task.  Tasks where any
    member has no valid repeat at all stay excluded (all-NaN row kept)."""
    reps = sorted(Y)
    out = {}
    stack = np.stack([Y[r] for r in reps])          # (n_rep, n_mem, n_task)
    filled = stack.copy()
    for m in range(stack.shape[1]):
        for t in range(stack.shape[2]):
            col = stack[:, m, t]
            if np.isnan(col).all():
                continue                            # stays excluded
            filled[np.isnan(col), m, t] = np.nanmean(col)
    for i, r in enumerate(reps):
        out[r] = filled[i]
    return out


def joint_permutations(n_members, n_tasks, rng):
    """Per-task identity permutations applied jointly across repeats."""
    return [rng.permutation(n_members) for _ in range(n_tasks)]


def a86_test(real_Y, real_members, clone_Y, clone_members, n_tasks_total):
    """Frozen A8.6 primary test. Returns the full result dict.

    A_real / A_clone are computed on each arm's own complete-case tasks (as
    frozen); D and its bootstrap CI use the INTERSECTION of both arms'
    complete-case tasks so the paired difference compares identical task
    identities.  If either arm excludes more than MAX_EXCLUDE_FRAC of tasks
    the main verdict degrades to INSUFFICIENT (coverage), per protocol.
    """
    rng = np.random.default_rng(SEED)
    d_rep, v_reps = 1, (2, 3)
    A_real, adv_real, cols_real = a86_statistic(
        real_Y, real_members, 'bare', d_rep, v_reps)
    A_clone, adv_clone, cols_clone = a86_statistic(
        clone_Y, clone_members, 'clone-c1', d_rep, v_reps)
    excl_real = 1 - len(cols_real) / n_tasks_total
    excl_clone = 1 - len(cols_clone) / n_tasks_total
    # paired D on the task intersection
    pos_real = {c: i for i, c in enumerate(cols_real)}
    pos_clone = {c: i for i, c in enumerate(cols_clone)}
    common = sorted(set(cols_real) & set(cols_clone))
    adv_r = np.array([adv_real[pos_real[c]] for c in common])
    adv_c = np.array([adv_clone[pos_clone[c]] for c in common])
    D = float(np.mean(adv_r) - np.mean(adv_c)) if common else float('nan')
    # permutation null within clone slots (exchangeable identical code)
    n_m = len(clone_members)
    null = np.empty(N_PERM)
    for b in range(N_PERM):
        perm = joint_permutations(n_m, clone_Y[d_rep].shape[1], rng)
        A_perm, _, _ = a86_statistic(clone_Y, clone_members, 'clone-c1',
                                     d_rep, v_reps, permute=perm)
        null[b] = A_perm
    p = (1 + int(np.sum(null >= A_real - DELTA))) / (N_PERM + 1)
    # task-level bootstrap of D on the intersection
    boots = np.empty(N_BOOT)
    brng = np.random.default_rng(SEED + 1)
    n_t = len(common)
    for b in range(N_BOOT):
        idx = brng.integers(0, n_t, n_t)
        boots[b] = np.mean(adv_r[idx]) - np.mean(adv_c[idx])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    coverage_ok = excl_real <= MAX_EXCLUDE_FRAC and excl_clone <= MAX_EXCLUDE_FRAC
    supported = bool(coverage_ok and p < 0.05 and lo > 0 and A_real > DELTA)
    if not coverage_ok:
        state = 'INSUFFICIENT'
    elif supported:
        state = 'SUPPORTED'
    elif np.isfinite(A_real):
        state = 'SUPPORTED_NOT_REACHED'
    else:
        state = 'INSUFFICIENT'
    result = {
        'estimand': 'A8.6 task-conditional advantage (discovery r1, validation r2-3)',
        'A_real': A_real, 'A_clone_obs': A_clone, 'D': D,
        'delta': DELTA, 'p_perm': p, 'D_ci95': [float(lo), float(hi)],
        'n_tasks_real': int(len(cols_real)),
        'n_tasks_clone': int(len(cols_clone)),
        'n_tasks_paired': int(n_t),
        'excluded_frac_real': round(excl_real, 4),
        'excluded_frac_clone': round(excl_clone, 4),
        'coverage_gate': f'<= {MAX_EXCLUDE_FRAC}',
        'state': state,
        'caveat': 'finite-R selection bias controlled only by the frozen '
                  'clone-null procedure; conclusions restricted to this panel, '
                  'condition, and task set',
    }
    if not coverage_ok:
        result['reason'] = ('coverage gate: excluded task fraction exceeds '
                            f'{MAX_EXCLUDE_FRAC} (real {excl_real:.3f}, '
                            f'clone {excl_clone:.3f})')
    # frozen sensitivity: within-task available-repeat mean imputation
    imp_real = impute_within_task(real_Y)
    imp_clone = impute_within_task(clone_Y)
    A_real_i, adv_ri, cols_ri = a86_statistic(imp_real, real_members, 'bare',
                                              d_rep, v_reps)
    A_clone_i, adv_ci, cols_ci = a86_statistic(imp_clone, clone_members,
                                               'clone-c1', d_rep, v_reps)
    common_i = sorted(set(cols_ri) & set(cols_ci))
    pos_ri = {c: i for i, c in enumerate(cols_ri)}
    pos_ci = {c: i for i, c in enumerate(cols_ci)}
    adv_r_i = np.array([adv_ri[pos_ri[c]] for c in common_i])
    adv_c_i = np.array([adv_ci[pos_ci[c]] for c in common_i])
    result['sensitivity_imputed'] = {
        'A_real': A_real_i, 'A_clone_obs': A_clone_i,
        'D': float(np.mean(adv_r_i) - np.mean(adv_c_i)) if common_i else None,
        'n_tasks_paired': len(common_i),
        'rule': 'within-task available-repeat mean imputation; tasks with a '
                'member missing all repeats still excluded',
    }
    return result


# --------------------------- E4 accounting ----------------------------------

def accounting(arm_names):
    """E4 rollup.  Continuation ledgers are merged first: rows whose full
    record is byte-identical across ledgers are migration copies and counted
    once; rows for the same cell with differing records are distinct real
    executions (or reconciled re-executions) and each counts.
    `ledger_row_attempts_upper_bound` is the naive all-rows figure,
    retained as an absolute upper bound."""
    out = {}
    total_tokens = total_attempts = total_calls = 0
    for name in arm_names:
        names = ARM_LEDGERS.get(name, [name])
        if not any((WP1R / n / 'ledger.sqlite').exists() for n in names):
            continue
        seen = set()
        attempts = calls = tokens = cells = dup_copies = 0
        raw_attempts = 0
        for ledger_name in names:
            ledger = WP1R / ledger_name / 'ledger.sqlite'
            if not ledger.exists():
                continue
            for c in load_cells(ledger):
                acc = c.get('accounting', {})
                cells += 1
                a = acc.get('http_attempts', 0)
                raw_attempts += a
                # full-record signature: migration copies are byte-identical
                # records (same worker_pid, trace, final_answer); distinct
                # re-executions differ and each counts
                sig = json.dumps(c, sort_keys=True, default=str)
                if sig in seen:
                    dup_copies += 1  # migration copy, not a new execution
                    continue
                seen.add(sig)
                attempts += a
                calls += acc.get('logical_calls', 0)
                t = acc.get('total_tokens')
                tokens += t if isinstance(t, int) else 0
        out[name] = {'cells': cells, 'logical_calls': calls,
                     'http_attempts': attempts,
                     'migration_copies_excluded': dup_copies,
                     'ledger_row_attempts_upper_bound': raw_attempts,
                     'known_total_tokens': tokens,
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
    # E1/E2 on the real panel (continuation ledgers merged)
    members, tasks, repeats, m_by_rep, manifest, _, dedup_real = \
        matrices(ARM_LEDGERS['eval_real'])
    report['dedup_eval_real'] = dedup_real
    pops = build_populations(members, tasks, m_by_rep, manifest)
    report['E1_C-rank_E2_C-comp'] = s3_stability(pops)
    report['panel'] = members
    report['n_tasks'] = len(tasks)
    report['repeats'] = repeats
    # A8.6 (requires eval_clone and all three repeats)
    if (WP1R / 'eval_clone' / 'ledger.sqlite').exists():
        cm, ct, cr, c_by_rep, cman, _, dedup_clone = \
            matrices(ARM_LEDGERS['eval_clone'])
        report['dedup_eval_clone'] = dedup_clone
        c_pops = build_populations(cm, ct, c_by_rep, cman)
        report['clone_arm_s3'] = s3_stability(c_pops)
        if {1, 2, 3} <= set(repeats) and {1, 2, 3} <= set(cr):
            primary = a86_test(m_by_rep, members, c_by_rep, cm,
                               n_tasks_total=len(tasks))
            report['E2_A86_clone_null'] = primary
            # frozen sensitivity: cells with two completed but disagreeing
            # executions excluded instead of first-completed (clone arm has
            # zero such cells, so the permutation null is identical)
            m2, t2, r2, mb2, _, _, _ = matrices(ARM_LEDGERS['eval_real'],
                                                 'nan')
            if {1, 2, 3} <= set(r2) and dedup_real['both_completed_differ']:
                A2, adv2, cols2 = a86_statistic(mb2, members, 'bare', 1, (2, 3))
                _, adv_c, cols_c = a86_statistic(c_by_rep, cm, 'clone-c1',
                                                 1, (2, 3))
                common2 = sorted(set(cols2) & set(cols_c))
                p2r = {c: i for i, c in enumerate(cols2)}
                p2c = {c: i for i, c in enumerate(cols_c)}
                ar2 = np.array([adv2[p2r[c]] for c in common2])
                ac2 = np.array([adv_c[p2c[c]] for c in common2])
                brng = np.random.default_rng(SEED + 1)
                boots = np.empty(N_BOOT)
                for b in range(N_BOOT):
                    idx = brng.integers(0, len(common2), len(common2))
                    boots[b] = np.mean(ar2[idx]) - np.mean(ac2[idx])
                lo, hi = np.percentile(boots, [2.5, 97.5])
                report['E2_sensitivity_double_executed_conflicts'] = {
                    'A_real': A2,
                    'D': float(np.mean(ar2) - np.mean(ac2)),
                    'D_ci95': [float(lo), float(hi)],
                    'p_perm_primary_reused': primary['p_perm'],
                    'n_tasks_paired': len(common2),
                    'n_cells_excluded':
                        len(dedup_real['both_completed_differ'])}
        else:
            report['E2_A86_clone_null'] = {
                'state': 'INSUFFICIENT',
                'reason': f'repeats present: real={repeats}, clone={cr}; '
                          'A8.6 requires repeats 1,2,3 in both arms'}
    report['E4_accounting'] = accounting(['eval_real', 'eval_clone', 'dev_real', 'pilot'])
    out = WP1R / 'analysis_report.json'
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: report[k].get('state', 'n/a') if isinstance(report[k], dict)
                      else report[k] for k in report}, ensure_ascii=False))
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
