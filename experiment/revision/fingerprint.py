"""Canonical W3 descriptive replay; no API calls or independent validation.

Retains the legacy SQL text transform to isolate the loader correction. It is a
lossy text fingerprint, not a SQL parser or a proof of semantic equivalence.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np

from experiment.revision.replay import (
    P2, ROOT, TARGET, digest, load_sources, membership, task_ids,
)
from experiment.revision.sensitivity import OUT, repeat_rows


def norm_sql(value):
    """Versioned legacy text transform; may alter literals/quoted identifiers."""
    if value is None or value == "":
        return "", frozenset()
    if not isinstance(value, str):
        raise ValueError("final_sql must be text or null")
    parts = value.replace(";", "").replace("`", "'").split("'")
    for i in range(0, len(parts), 2):
        parts[i] = parts[i].lower()
    normalized = " ".join("'".join(parts).split())
    return normalized, frozenset(normalized.split())


def spearman(xs, ys):
    """Average tied ranks; undefined correlations are null, never NaN JSON."""
    def rank(values):
        _, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
        ends = counts.cumsum()
        return ((ends - counts + 1 + ends) / 2)[inverse]
    if len(xs) < 2:
        return None
    x, y = rank(xs), rank(ys)
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def candidate_records(groups, mem, tasks):
    """Only admission-mapped candidates; require every declared task record."""
    records, cells, arms = {}, {}, {}
    for (builder, seed, arm), names in sorted(mem.items()):
        cell = cells.setdefault((builder, seed), [])
        for h in names:
            if h in arms:
                raise ValueError("candidate appears in multiple membership units: " + h)
            arms[h] = arm
            cell.append(h)
            for task in tasks:
                row = groups['AD' if arm in 'AD' else 'BC'][TARGET, h, task, 0, False]
                for field in ('n_llm_calls', 'n_execs'):
                    if not isinstance(row[field], int) or row[field] < 0:
                        raise ValueError('invalid recorded trajectory count: ' + field)
                norm_sql(row['final_sql'])
                records[h, task] = row
    return records, {k: sorted(v) for k, v in sorted(cells.items())}, arms


def pair_summary(records, cells, arms, tasks):
    normalized = {key: norm_sql(row['final_sql']) for key, row in records.items()}
    pairs = []
    same_total = same_disagreement = 0
    for (builder, seed), names in cells.items():
        for a, b in itertools.combinations(names, 2):
            disagreement = calls = executions = 0
            sql_diff = available_agree = identical_sql = identical_sql_dis = 0
            jaccards = []
            for t in tasks:
                ra, rb = records[a, t], records[b, t]
                different = ra['official_correct'] != rb['official_correct']
                disagreement += different
                calls += ra['n_llm_calls'] != rb['n_llm_calls']
                executions += ra['n_execs'] != rb['n_execs']
                sa, ta = normalized[a, t]
                sb, tb = normalized[b, t]
                if sa and sb:
                    if sa == sb:
                        identical_sql += 1
                        identical_sql_dis += different
                    if not different:
                        available_agree += 1
                        sql_diff += sa != sb
                        jaccards.append(len(ta & tb) / len(ta | tb))
            same_total += identical_sql
            same_disagreement += identical_sql_dis
            pairs.append(dict(builder=builder, seed=seed, h1=a, h2=b,
                within_arm=arms[a] == arms[b], n_tasks=len(tasks),
                outcome_disagreements=disagreement, call_differences=calls,
                execution_differences=executions,
                n_nonempty_sql_verdict_agree=available_agree,
                sql_differences_given_agree=sql_diff,
                mean_sql_dissimilarity_given_agree=1-float(np.mean(jaccards)) if jaccards else None,
                all_channels_identical=(disagreement == calls == executions == sql_diff == 0
                                        and available_agree == len(tasks))))
    def correlation(selected):
        eligible = [p for p in selected if p['mean_sql_dissimilarity_given_agree'] is not None]
        return dict(n_pairs=len(selected), n_eligible=len(eligible),
            rho=spearman([p['mean_sql_dissimilarity_given_agree'] for p in eligible],
                         [p['outcome_disagreements']/p['n_tasks'] for p in eligible]))
    return dict(n_pairs=len(pairs),
        all_pairs_correlation=correlation(pairs),
        within_arm_correlation=correlation([p for p in pairs if p['within_arm']]),
        identical_normalized_sql=dict(n=same_total, verdict_disagreements=same_disagreement,
                                      rate=same_disagreement/same_total if same_total else None),
        outcome_identical_pairs=sum(p['outcome_disagreements'] == 0 for p in pairs),
        all_channels_identical_pairs=sum(p['all_channels_identical'] for p in pairs),
        pairs=pairs)


def rerun_summary(groups, repeats, mem, tasks, records):
    names = sorted(h for (b, s, a), hs in mem.items() if a in 'AD' for h in hs[:2])
    # Uses the same full-coverage and source-hash check as the R2 reanalysis.
    repeat_rows(groups['AD'], repeats, 'r2_pass1', names, tasks)
    counters = {k: dict(n=0, changed=0) for k in ('calls', 'sql', 'verdict')}
    changed_jaccards = []
    for h in names:
        for t in tasks:
            original = records[h, t]
            repeated = repeats['r2_pass1'][TARGET, h, t, 0, True]
            if not isinstance(repeated['n_llm_calls'], int) or repeated['n_llm_calls'] < 0:
                raise ValueError('invalid repeated call count')
            for channel, field in (('calls', 'n_llm_calls'), ('verdict', 'official_correct')):
                counters[channel]['n'] += 1
                counters[channel]['changed'] += int(original[field] != repeated[field])
            sa, ta = norm_sql(original['final_sql'])
            sb, tb = norm_sql(repeated['final_sql'])
            if sa and sb:
                counters['sql']['n'] += 1
                counters['sql']['changed'] += int(sa != sb)
                if sa != sb:
                    changed_jaccards.append(len(ta & tb)/len(ta | tb))
    for c in counters.values():
        c['rate'] = c['changed']/c['n'] if c['n'] else None
    return dict(n_harnesses=len(names), channels=counters,
        mean_jaccard_when_sql_changed=float(np.mean(changed_jaccards)) if changed_jaccards else None,
        n_sql_changed=len(changed_jaccards))


def main():
    groups, inventory, audit = load_sources({'AD': P2/'primary_input_manifest.json',
                                            'BC': P2/'bc_input_manifest.json'})
    repeats, repeat_inventory, _ = load_sources({'r2_pass1': OUT/'inputs/r2_pass1.json'})
    mem, gen_inventory, _ = membership()
    split = ROOT/'experiment/phase2/split_p2_test_core.json'
    tasks = task_ids(split)
    records, cells, arms = candidate_records(groups, mem, tasks)
    result = dict(analysis_version='fingerprint-20260910-v1',
        scope='post-hoc descriptive, conditional on current records; no independent validation, no inferential p-values or CIs',
        normalization='legacy W3 text transform retained to isolate loader change; lossy, not semantic SQL equivalence',
        weighting='correlations over within-cell candidate pairs; pairs are dependent; no inferential sample-size claim',
        n_cells=len(cells), n_harnesses=len(arms), n_tasks=len(tasks),
        canonical_source_audit=audit, summary=pair_summary(records, cells, arms, tasks),
        rerun=rerun_summary(groups, repeats, mem, tasks, records))
    result['inputs'] = inventory + repeat_inventory + gen_inventory + [
        dict(path=p.relative_to(ROOT).as_posix(), sha256=digest(p)) for p in
        (split, ROOT/'experiment/revision/replay.py', ROOT/'experiment/revision/sensitivity.py', Path(__file__))]
    (OUT/'fingerprint.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k,v in result['summary'].items() if k != 'pairs'}, indent=2))
    print(result['rerun'])


if __name__ == '__main__':
    main()
