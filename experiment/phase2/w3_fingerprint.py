"""W3 post-hoc analysis: richer behavioral fingerprints on the archived confirmatory
cells (zero new API calls). Extends the binary-correctness fingerprint with three
channels already present in every run record: final-SQL artifact, LLM-call count,
and execution count.

Questions (all exploratory, post-hoc on the confirmatory data):
  1. Output-level collapse: for within-cell harness pairs, how often do harnesses
     agree on correctness but emit different SQL?  (P(SQL differs | verdict agrees))
     And the consistency check P(verdict differs | SQL identical) ~ 0.
  2. Does artifact similarity predict outcome disagreement?  Spearman between
     mean pairwise final-SQL token-Jaccard and outcome disagreement, to compare
     against the Phase-I code-similarity result (rho = -0.01).
  3. Trajectory fingerprint: per-harness call/exec profiles; among outcome-identical
     pairs, how many differ in trajectory profile; call-count vs accuracy.
  4. Fingerprint stability across reruns: same harness, cached vs cache-off
     (R2 data), how often do n_llm_calls / final_sql change -- the noise floor
     for the richer channels.
  5. Multi-channel collapse: fraction of within-cell pairs identical on every
     channel vs correctness-only.
"""
import itertools
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P2 = ROOT / "artifacts" / "phase2"

split = json.loads((ROOT / "experiment/phase2/split_p2_test_core.json").read_text())
CORE = {f"{d}#{i}" for d, idxs in split["by_db"].items() for i in idxs}

# ---------------------------------------------------------------- load cells
recs = {}                      # (h, t) -> record, last-seen wins (r2 convention)
for pat in ("ad_*.jsonl", "bc_*.jsonl"):
    for p in sorted(P2.glob(pat)):
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            h, t = r.get("harness_id"), r.get("task_id")
            if h and h.startswith("p2_") and t in CORE and r.get("repeat", 0) == 0:
                recs[(h, t)] = r

harnesses = sorted({h for h, t in recs})
by_cell = defaultdict(list)
for h in harnesses:
    p = h.split("_")                      # p2, arm, builder, seed, slot
    by_cell[(p[2], p[3])].append(h)

# ---------------------------------------------------------------- channels
def norm_sql(s):
    """Normalize SQL for text comparison. Lowercase only outside string literals
    (literal case is verdict-relevant: 'Eur' vs 'EUR' flips the official judge)."""
    if not s:
        return "", frozenset()
    parts = s.replace(";", "").replace("`", "'").split("'")
    for i in range(0, len(parts), 2):        # even indices are outside literals
        parts[i] = parts[i].lower()
    joined = " ".join("'".join(parts).split())
    return joined, frozenset(joined.split())

sql_norm, sql_tok = {}, {}
for (h, t), r in recs.items():
    s, toks = norm_sql(r.get("final_sql"))
    sql_norm[(h, t)], sql_tok[(h, t)] = s, toks

def get(h, t, k):
    r = recs.get((h, t))
    return r.get(k) if r else None

# ---------------------------------------------------------------- pair stats
def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                rk[order[k]] = avg
            i = j + 1
        return rk
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")

pairs = []                     # one row per within-cell pair
for cell, hs in sorted(by_cell.items()):
    hs = [h for h in hs if all((h, t) in recs for t in CORE)]
    if len(hs) < 2:
        continue
    for h1, h2 in itertools.combinations(hs, 2):
        dis = 0                # verdict disagreements
        sql_diff = 0           # normalized final SQL differs
        jac = 0.0              # token Jaccard accumulator
        calls_diff = 0         # n_llm_calls differ
        execs_diff = 0         # n_execs differ
        both_sql = 0
        for t in CORE:
            r1, r2 = recs[(h1, t)], recs[(h2, t)]
            v1, v2 = r1.get("official_correct"), r2.get("official_correct")
            dis += (v1 != v2)
            if v1 == v2:
                s1, s2 = sql_norm[(h1, t)], sql_norm[(h2, t)]
                if s1 and s2:
                    both_sql += 1
                    sql_diff += (s1 != s2)
                    a, b = sql_tok[(h1, t)], sql_tok[(h2, t)]
                    u = len(a | b)
                    jac += (len(a & b) / u if u else 1.0)
            c1, c2 = r1.get("n_llm_calls"), r2.get("n_llm_calls")
            if c1 is not None and c2 is not None:
                calls_diff += (c1 != c2)
            e1, e2 = r1.get("n_execs"), r2.get("n_execs")
            if e1 is not None and e2 is not None:
                execs_diff += (e1 != e2)
        n = len(CORE)
        pairs.append({
            "cell": f"{cell[0]}/{cell[1]}", "h1": h1, "h2": h2,
            "arm1": h1.split("_")[1], "arm2": h2.split("_")[1],
            "disagree": dis / n,
            "sql_diff_given_agree": (sql_diff / both_sql) if both_sql else None,
            "mean_jac_given_agree": (jac / both_sql) if both_sql else None,
            "calls_diff": calls_diff / n, "execs_diff": execs_diff / n,
            "all_identical": dis == 0 and calls_diff == 0 and execs_diff == 0
                              and sql_diff == 0 and both_sql == n,
        })

# consistency check: verdict disagreement when normalized SQL identical
n_sql_same = n_sql_same_dis = 0
for cell, hs in sorted(by_cell.items()):
    hs = [h for h in hs if all((h, t) in recs for t in CORE)]
    for h1, h2 in itertools.combinations(hs, 2):
        for t in CORE:
            s1, s2 = sql_norm[(h1, t)], sql_norm[(h2, t)]
            if s1 and s2 and s1 == s2:
                n_sql_same += 1
                n_sql_same_dis += (recs[(h1, t)]["official_correct"]
                                   != recs[(h2, t)]["official_correct"])

# ---------------------------------------------------------------- per-harness cost
cost = {}
for h in harnesses:
    rows = [recs[(h, t)] for t in CORE if (h, t) in recs]
    if len(rows) == len(CORE):
        acc = sum(r["official_correct"] for r in rows) / len(rows)
        cost[h] = {
            "acc": acc,
            "mean_calls": sum(r["n_llm_calls"] for r in rows) / len(rows),
            "frac_multicall": sum(r["n_llm_calls"] > 1 for r in rows) / len(rows),
            "mean_execs": sum(r["n_execs"] for r in rows) / len(rows),
        }

# outcome-identical pairs and their trajectory profiles
ident = [p for p in pairs if p["disagree"] == 0]
ident_traj_diff = [p for p in ident if p["calls_diff"] > 0]

# ---------------------------------------------------------------- rerun stability (R2)
r2 = {}
for line in (P2 / "r2_cacheoff.jsonl").read_text(encoding="utf-8", errors="ignore").splitlines():
    if line.strip():
        r = json.loads(line)
        if r["task_id"] in CORE:
            r2[(r["harness_id"], r["task_id"])] = r
stab = {"calls": [0, 0], "sql": [0, 0], "verdict": [0, 0]}
rerun_jac = []                # token Jaccard between the two runs' SQL, when it changed
for (h, t), rr in r2.items():
    ro = recs.get((h, t))
    if not ro:
        continue
    if rr.get("n_llm_calls") is not None and ro.get("n_llm_calls") is not None:
        stab["calls"][0] += 1
        stab["calls"][1] += (rr["n_llm_calls"] != ro["n_llm_calls"])
    s1, t1 = norm_sql(rr.get("final_sql"))
    s2, t2 = norm_sql(ro.get("final_sql"))
    if s1 and s2:
        stab["sql"][0] += 1
        stab["sql"][1] += (s1 != s2)
        if s1 != s2:
            u = len(t1 | t2)
            rerun_jac.append(len(t1 & t2) / u if u else 1.0)
    stab["verdict"][0] += 1
    stab["verdict"][1] += (rr["official_correct"] != ro["official_correct"])

# ---------------------------------------------------------------- report
within_arm = [p for p in pairs if p["arm1"] == p["arm2"]]
def mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None

out = {
    "n_pairs": len(pairs),
    "n_pairs_within_arm": len(within_arm),
    "mean_outcome_disagreement": round(mean([p["disagree"] for p in pairs]), 4),
    "frac_pairs_outcome_identical": round(len(ident) / len(pairs), 4),
    "sql_diff_given_verdict_agree": round(mean([p["sql_diff_given_agree"] for p in pairs]), 4),
    "mean_token_jaccard_given_verdict_agree": round(mean([p["mean_jac_given_agree"] for p in pairs]), 4),
    "verdict_disagree_given_sql_identical": round(n_sql_same_dis / max(1, n_sql_same), 4),
    "n_sql_identical_cells": n_sql_same,
    "calls_diff_rate": round(mean([p["calls_diff"] for p in pairs]), 4),
    "execs_diff_rate": round(mean([p["execs_diff"] for p in pairs]), 4),
    "spearman_sqlsim_vs_disagreement": round(spearman(
        [1 - p["mean_jac_given_agree"] for p in pairs],
        [p["disagree"] for p in pairs]), 4),
    "spearman_sqlsim_vs_disagreement_within_arm": round(spearman(
        [1 - p["mean_jac_given_agree"] for p in within_arm],
        [p["disagree"] for p in within_arm]), 4),
    "n_pairs_within_arm_used": len(within_arm),
    "outcome_identical_pairs": len(ident),
    "outcome_identical_but_calls_differ": len(ident_traj_diff),
    "frac_pairs_identical_all_channels": round(
        mean([1.0 if p["all_identical"] else 0.0 for p in pairs]), 4),
    "rerun_stability": {k: {"n": v[0], "changed": v[1],
                            "rate": round(v[1] / max(1, v[0]), 4)}
                        for k, v in stab.items()},
    "rerun_sql_mean_jaccard_when_changed": round(
        sum(rerun_jac) / len(rerun_jac), 4) if rerun_jac else None,
    "n_rerun_sql_changed": len(rerun_jac),
}
# call count vs accuracy, per arm
arm_calls = defaultdict(list)
for h, c in cost.items():
    arm_calls[h.split("_")[1]].append(c)
out["per_arm_cost"] = {
    arm: {"n": len(cs),
          "mean_calls": round(mean([c["mean_calls"] for c in cs]), 3),
          "frac_multicall": round(mean([c["frac_multicall"] for c in cs]), 3),
          "mean_acc": round(mean([c["acc"] for c in cs]), 4)}
    for arm, cs in sorted(arm_calls.items())}

(P2 / "w3_fingerprint.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))

# a few example outcome-identical pairs with differing trajectories, for the paper
ex = ident_traj_diff[:5]
print("\nexample outcome-identical pairs with differing call profiles:")
for p in ex:
    c1, c2 = cost.get(p["h1"], {}), cost.get(p["h2"], {})
    print(f"  {p['cell']:12s} {p['h1']:32s} calls={c1.get('mean_calls'):.2f} "
          f"vs {p['h2']:32s} calls={c2.get('mean_calls'):.2f}  "
          f"task-level calls_diff={p['calls_diff']:.2%}")
