"""LOHO value-prediction on EXECUTABLE harnesses (TTHE/BIRD outcome matrix).

Same protocol as day0_sanity.py but the population is executable harnesses (bare, react,
Builder-generated candidates) and harness features are derived from code/description.

H0 = bare.  delta(x,H) in {-1,0,+1}.  LOHO over all non-bare harnesses.
Setting A (pure pre-execution): task text + harness code/description features. No model
confidence available (paratera gives no logprobs) so Setting B is out of scope for this pilot.

Usage: python experiment/loho_exec.py [--matrix artifacts/outcomes/tthe_bird_matrix.parquet]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "artifacts" / "day1"
OUT.mkdir(parents=True, exist_ok=True)
SEED = 1234
TAU_GRID = np.linspace(0.0, 0.6, 25)


def stable_item_hash(s: str) -> int:
    return int(hashlib.sha1(s.encode()).hexdigest()[:8], 16)


def harness_struct_features(code: str, desc: str) -> list[float]:
    return [
        float(len(code)) / 4000.0,
        float(code.count("self.llm(")),
        float(code.count("self.execute(")),
        float(len(re.findall(r"for .*range|while ", code))),
        float(int(bool(re.search(r"vote|majority|n=3|n=2", code, re.I)))),
        float(int(bool(re.search(r"repair|retry|rewrite|again", code, re.I)))),
        float(int(bool(re.search(r"verify|check|valid", code, re.I)))),
        float(int(bool(re.search(r"hint|evidence", code, re.I)))),
        float(len(desc)) / 400.0,
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", default="artifacts/outcomes/tthe_bird_matrix.parquet")
    ap.add_argument("--harnesses", default=None,
                    help="comma-separated subset (must include bare); default: all in matrix")
    ap.add_argument("--out-tag", default="LOHO_RESULTS", help="output JSON name in artifacts/day1/")
    args = ap.parse_args()
    mpath = ROOT / args.matrix
    t0 = time.time()

    df = pd.read_parquet(mpath)
    if args.harnesses:
        keep = [s.strip() for s in args.harnesses.split(",")]
        df = df[df["harness_id"].isin(keep)]
    df = df[df["baseline_correct"].notna()].copy()
    H0 = "bare"
    configs = sorted(df["harness_id"].unique())
    assert H0 in configs
    cands = [c for c in configs if c != H0]
    print(f"[load] {len(df)} rows | {df['task_id'].nunique()} tasks | {len(cands)} candidate harnesses + {H0}")

    # ---- stats: L1 headroom ----
    wide = df.pivot_table(index="task_id", columns="harness_id", values="harness_correct")
    per_cfg = df.groupby("harness_id")["harness_correct"].mean().sort_values(ascending=False)
    best_fixed, best_acc = per_cfg.index[0], float(per_cfg.iloc[0])
    oracle = wide.max(axis=1).mean()
    head_pp = 100 * (oracle - best_acc)
    stats = {"n_tasks": int(df["task_id"].nunique()), "n_harnesses": len(configs),
             "per_harness_acc": per_cfg.round(4).to_dict(), "best_fixed": best_fixed,
             "best_fixed_acc": best_acc, "H0_acc": float(per_cfg[H0]),
             "oracle_acc": float(oracle), "headroom_vs_best_fixed_pp": head_pp,
             "headroom_vs_H0_pp": 100 * (float(oracle) - float(per_cfg[H0]))}
    print(f"[stats] H0={per_cfg[H0]:.3f} | best fixed {best_fixed}={best_acc:.3f} | "
          f"oracle={oracle:.3f} | headroom {head_pp:.1f}pp")

    dfa = df[df["harness_id"] != H0].copy()
    dfa["delta"] = dfa["harness_correct"] - dfa["baseline_correct"]
    stats["delta_prevalence"] = {k: float(v) for k, v in
                                 dfa["delta"].value_counts(normalize=True).sort_index().items()}
    print(f"[stats] delta prevalence: {stats['delta_prevalence']}")

    # ---- features ----    (Setting A only: task text + harness code/desc)
    qmap = df.drop_duplicates("task_id").set_index("task_id")["task_text"]
    tfv = TfidfVectorizer(max_features=256, ngram_range=(1, 2), min_df=2, sublinear_tf=True,
                          dtype=np.float32)
    tfv.fit(dfa["task_text"].fillna(""))
    X_task = tfv.transform(dfa["task_text"].fillna(""))

    _hd = dfa.drop_duplicates("harness_id").set_index("harness_id")
    hcodes = _hd["harness_text"].to_dict()
    hdesc = _hd["harness_description"].to_dict()
    hv = TfidfVectorizer(max_features=96, ngram_range=(1, 2), sublinear_tf=True, dtype=np.float32)
    hv.fit([hcodes[c] + " " + hdesc.get(c, "") for c in cands])
    rows_h_text = hv.transform(dfa["harness_id"].map(lambda c: hcodes[c] + " " + hdesc.get(c, "")))
    rows_h_struct = sparse.csr_matrix(np.array(
        [harness_struct_features(hcodes[c], hdesc.get(c, "")) for c in dfa["harness_id"]],
        dtype=np.float32))
    X_H = sparse.hstack([rows_h_text, rows_h_struct], format="csr")

    XA = sparse.hstack([X_task, X_H], format="csr")     # full
    XT = X_task.tocsr()                                  # task-only control
    XH = X_H.tocsr()                                     # harness-only control

    # closed-set: harness-id one-hot
    cid = {c: i for i, c in enumerate(cands)}
    X_id = sparse.hstack([X_task, sparse.csr_matrix(
        (np.ones(len(dfa), dtype=np.float32),
         (np.arange(len(dfa)), dfa["harness_id"].map(cid).values)),
        shape=(len(dfa), len(cands)))], format="csr")

    y_pos = (dfa["delta"] == 1).values.astype(int)
    y_neg = (dfa["delta"] == -1).values.astype(int)
    delta = dfa["delta"].values.astype(int)
    cfg_of_row = dfa["harness_id"].values
    task_of_row = dfa["task_id"].values
    bc = dfa["baseline_correct"].values.astype(int)
    hc = dfa["harness_correct"].values.astype(int)
    tune_half = np.array([(stable_item_hash(t) % 10) < 2 for t in task_of_row])

    def fit_binary(Xtr, ytr, Xte):
        from sklearn.linear_model import SGDClassifier
        clf = SGDClassifier(loss="log_loss", alpha=1e-5, max_iter=30, tol=1e-3, random_state=SEED)
        clf.fit(Xtr, ytr)
        return clf.predict_proba(Xte)[:, 1]

    def loho(Xmat, tag):
        folds, pooled = [], []
        for held in cands:
            te = cfg_of_row == held
            tr = ~te
            if y_pos[te].sum() == 0 or y_pos[tr].sum() == 0:
                continue
            p_pos = fit_binary(Xmat[tr], y_pos[tr], Xmat[te])
            p_neg = fit_binary(Xmat[tr], y_neg[tr], Xmat[te])
            auc = roc_auc_score(y_pos[te], p_pos) if 0 < y_pos[te].sum() < te.sum() else np.nan
            ap = average_precision_score(y_pos[te], p_pos) if y_pos[te].sum() else np.nan
            cls = np.argmax(np.stack([p_pos, p_neg, 1 - p_pos - p_neg]), axis=0) - 1
            f1m = f1_score(delta[te], cls, average="macro", labels=[-1, 0, 1])
            folds.append({"held_out": held, "auroc_pos": float(auc), "auprc_pos": float(ap),
                          "macro_f1": float(f1m), "prev_pos": float(y_pos[te].mean()),
                          "prev_neg": float(y_neg[te].mean())})
            pooled.append(pd.DataFrame({
                "task_id": task_of_row[te], "config": held, "tune": tune_half[te],
                "p_pos": p_pos, "p_neg": p_neg, "baseline_correct": bc[te],
                "harness_correct": hc[te], "delta": delta[te]}))
        print(f"  [{tag}] {len(folds)} folds ({time.time()-t0:.0f}s)", flush=True)
        return folds, (pd.concat(pooled, ignore_index=True) if pooled else pd.DataFrame())

    results = {}
    folds_A, pooled_A = loho(XA, "A")
    folds_T, _ = loho(XT, "T")
    folds_H, _ = loho(XH, "H")
    results["loho_A"] = folds_A
    results["loho_task_only"] = folds_T
    results["loho_harness_only"] = folds_H

    # closed-set upper-ish (harness id visible), random-item split
    tr_id = ~tune_half
    results["closedset_harness_id_auroc"] = float(roc_auc_score(
        y_pos[tune_half], fit_binary(X_id[tr_id], y_pos[tr_id], X_id[tune_half]))) \
        if 0 < y_pos[tune_half].sum() else None
    results["closedset_task_only_auroc"] = float(roc_auc_score(
        y_pos[tune_half], fit_binary(XT[tr_id], y_pos[tr_id], XT[tune_half])))

    def summarize(folds):
        a = pd.DataFrame(folds)
        return {"mean_auroc_pos": float(a["auroc_pos"].mean()), "min": float(a["auroc_pos"].min()),
                "max": float(a["auroc_pos"].max()), "mean_macro_f1": float(a["macro_f1"].mean())}
    results["summary"] = {"A": summarize(folds_A), "task_only": summarize(folds_T),
                          "harness_only": summarize(folds_H)}

    # ---- policy (argmax over candidates + threshold, tune/eval halves) ----
    def policy_eval(pooled):
        if pooled.empty:
            return {}
        d = pooled.copy()
        d["value"] = d["p_pos"] - d["p_neg"]
        tune, ev = d[d["tune"]], d[~d["tune"]]
        tune_acc = tune.groupby("config")["harness_correct"].mean()
        best_cfg = tune_acc.idxmax()
        vr = tune.loc[tune.groupby("task_id")["value"].idxmax()]
        best_tau, best_a = 0.2, -1.0
        for tau in TAU_GRID:
            use = (vr["value"] > tau).values
            a = float(np.where(use, vr["harness_correct"].values, vr["baseline_correct"].values).mean())
            if a > best_a:
                best_a, best_tau = a, float(tau)
        br = ev.loc[ev.groupby("task_id")["value"].idxmax()]
        use = (br["value"] > best_tau).values
        final = np.where(use, br["harness_correct"].values, br["baseline_correct"].values)
        base_acc = float(ev.groupby("task_id")["baseline_correct"].first().mean())
        bf_acc = float(ev[ev["config"] == best_cfg]["harness_correct"].mean())
        return {"tau": best_tau, "best_fixed_config": best_cfg, "H0_acc": base_acc,
                "best_fixed_acc": bf_acc, "policy_acc": float(final.mean()),
                "gain_vs_H0_pp": 100 * (float(final.mean()) - base_acc),
                "gain_vs_best_fixed_pp": 100 * (float(final.mean()) - bf_acc),
                "intervention_rate": float(use.mean()),
                "harm_rate_on_intervention": float((br["delta"].values[use] == -1).mean()) if use.any() else 0.0,
                "repair_rate_on_intervention": float((br["delta"].values[use] == 1).mean()) if use.any() else 0.0,
                "oracle_acc": float(ev.groupby("task_id").apply(
                    lambda x: max(x["harness_correct"].max(), x["baseline_correct"].max()),
                    include_groups=False).mean())}

    results["policy"] = policy_eval(pooled_A)

    # bootstrap CI on policy gain vs best fixed (eval half, task-level)
    d = pooled_A.copy()
    d["value"] = d["p_pos"] - d["p_neg"]
    ev = d[~d["tune"]]
    br = ev.loc[ev.groupby("task_id")["value"].idxmax()]
    use = (br["value"] > results["policy"]["tau"]).values
    final = pd.Series(np.where(use, br["harness_correct"].values, br["baseline_correct"].values),
                      index=br.set_index("task_id").index)
    bf = ev[ev["config"] == results["policy"]["best_fixed_config"]].set_index("task_id")["harness_correct"]
    rng = np.random.default_rng(SEED)
    tasks_u = final.index.unique()
    gains = []
    for _ in range(500):
        samp = rng.choice(tasks_u, size=len(tasks_u), replace=True)
        gains.append(final.loc[samp].mean() - bf.loc[samp].mean())
    results["policy"]["gain_vs_best_fixed_ci95"] = [float(np.percentile(gains, 2.5)),
                                                    float(np.percentile(gains, 97.5))]

    (OUT / f"{args.out_tag}.json").write_text(json.dumps(
        {"stats": stats, **results}, indent=2))
    print(json.dumps({"stats": {k: v for k, v in stats.items() if k != "per_harness_acc"},
                      "summary": results["summary"],
                      "closedset": {k: results[k] for k in
                                    ["closedset_harness_id_auroc", "closedset_task_only_auroc"]},
                      "policy": results["policy"]}, indent=2))
    print(f"[done] {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
