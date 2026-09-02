"""Day-0 sanity experiment: is harness marginal value learnable & open-set generalizable?

Data: external/fragility-grid (2608.21382) — 12 models x 26 harness configs x 3679 items,
one correctness bit per (model, item, config). Config-level harnesses (prompt format,
option permutation, scoring mode). This is a SANITY test for the value-prediction
formulation, not a paper experiment.

Delta definition (frozen): H0 = reference config (gen|letter_plain|p0).
    delta(x, H, M) = Y(x, H, M) - Y(x, H0, M) in {-1, 0, +1}

Settings (kept separate, PROBLEM_FREEZE.md section 2):
    A  pure pre-execution: task text + harness structural features + model id
    B  after-raw:          A + ll_margin (raw model's top-2 likelihood margin)

Protocol: leave-one-harness-out over all 25 non-reference configs. Threshold tau tuned
inside train folds only. No random item split is ever reported as "open-set".

Usage:  python experiment/day0_sanity.py
Outputs: artifacts/day0/{outcome_matrix.parquet, day0_stats.json, loho_results.json}
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
RECORDS = ROOT / "external" / "fragility-grid" / "results" / "fragility" / "records"
LEGEND = ROOT / "external" / "fragility-grid" / "results" / "fragility" / "config_legend.json"
OUT = ROOT / "artifacts" / "day0"
OUT.mkdir(parents=True, exist_ok=True)

SEED = 1234
N_TFIDF = 384
TAU_GRID = np.linspace(0.0, 0.6, 25)


# ----------------------------------------------------------------- load data
def load_rows() -> pd.DataFrame:
    recs = []
    for p in sorted(RECORDS.glob("*__*.jsonl")):
        bench, model = p.stem.split("__", 1)
        with open(p, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                for ck, bit in r["bits"].items():
                    recs.append(
                        (bench, r["item_id"], r["question"], model, r["gold"],
                         r.get("ll_margin"), ck, int(bit))
                    )
    df = pd.DataFrame(recs, columns=[
        "bench", "item_id", "question", "model", "gold", "ll_margin", "config", "correct"])
    return df


def stable_item_hash(item_id: str) -> int:
    return int(hashlib.sha1(item_id.encode()).hexdigest()[:8], 16)


def main() -> None:
    t0 = time.time()
    legend = json.loads(LEGEND.read_text())
    ref = legend["_meta"]["ref_config"]
    configs = [k for k in legend if k != "_meta"]
    print(f"[load] reference config H0 = {ref}, {len(configs)} configs")

    df = load_rows()
    n_models = df["model"].nunique()
    n_items = df["item_id"].nunique()
    print(f"[load] {len(df):,} rows | {n_models} models x {n_items} items x {len(configs)} configs "
          f"({time.time()-t0:.0f}s)")

    # baseline correctness per (model, item) under H0
    base = df[df["config"] == ref].set_index(["model", "item_id"])["correct"]
    df["baseline_correct"] = df.set_index(["model", "item_id"]).index.map(base)
    dfa = df[df["config"] != ref].copy()
    dfa["delta"] = dfa["correct"] - dfa["baseline_correct"]
    assert dfa["baseline_correct"].notna().all()

    # ------------------------------------------------------------ A2 stats
    stats = {"n_rows": len(df), "n_models": n_models, "n_items": n_items,
             "n_configs": len(configs), "ref_config": ref}
    per_cfg = df.groupby("config")["correct"].mean().sort_values(ascending=False)
    per_model = df.groupby("model")["correct"].mean().sort_values(ascending=False)
    stats["per_config_accuracy"] = per_cfg.to_dict()
    stats["per_model_accuracy"] = per_model.round(4).to_dict()
    best_fixed, best_acc = per_cfg.index[0], float(per_cfg.iloc[0])
    stats["best_fixed_config"], stats["best_fixed_acc"] = best_fixed, best_acc

    wide = df.pivot_table(index=["model", "item_id"], columns="config", values="correct")
    oracle = wide.max(axis=1)
    stats["oracle_portfolio_acc"] = float(oracle.mean())
    stats["oracle_portfolio_gain_vs_best_fixed_pp"] = 100 * (stats["oracle_portfolio_acc"] - best_acc)
    stats["oracle_portfolio_gain_vs_ref_pp"] = 100 * (stats["oracle_portfolio_acc"]
                                                      - float(per_cfg[ref]))
    stats["delta_prevalence"] = {k: float(v) for k, v in
                                 dfa["delta"].value_counts(normalize=True).sort_index().items()}

    # pairwise repair / regression vs reference + complementarity
    acc_w = wide.mean(axis=0)
    rep = pd.DataFrame(index=configs, columns=configs, dtype=float)
    for a in configs:
        for b in configs:
            ra = wide[a].values.astype(int)
            rb = wide[b].values.astype(int)
            rep.loc[a, b] = float(((ra == 0) & (rb == 1)).mean())  # a wrong -> b right
    stats["repair_vs_ref"] = {c: float(rep.loc[c, ref]) for c in configs if c != ref}
    stats["regression_vs_ref"] = {c: float(rep.loc[ref, c]) for c in configs if c != ref}
    top = per_cfg.head(8).index.tolist()
    union = wide[top].max(axis=1)
    top_union_fix = float((union.values > wide[ref].values).mean())
    stats["top8_union_repair_of_ref_errors"] = top_union_fix
    stats["pairwise_repair_matrix_top8"] = rep.loc[top, top].round(4).to_dict()

    print(f"[stats] best fixed {best_fixed} = {best_acc:.4f} | oracle {stats['oracle_portfolio_acc']:.4f} "
          f"| headroom {stats['oracle_portfolio_gain_vs_best_fixed_pp']:.1f}pp", flush=True)

    # ------------------------------------------------------------- features
    # task: benchmark one-hot + TF-IDF(question). model: one-hot (day-0 caveat).
    # harness: structural, transferable to unseen configs (NO config id).
    questions = df.drop_duplicates("item_id").set_index("item_id")["question"]
    tfv = TfidfVectorizer(max_features=N_TFIDF, ngram_range=(1, 2), min_df=5,
                          sublinear_tf=True, dtype=np.float32)
    tfv.fit(questions.values)
    qmap = {q: i for i, q in enumerate(questions.index)}
    X_text = tfv.transform(dfa["item_id"].map(questions).fillna(""))

    models_sorted = sorted(dfa["model"].unique())
    m_idx = {m: i for i, m in enumerate(models_sorted)}
    X_model = sparse.csr_matrix(
        (np.ones(len(dfa), dtype=np.float32),
         (np.arange(len(dfa)), dfa["model"].map(m_idx).values)),
        shape=(len(dfa), len(models_sorted)))

    benches = sorted(dfa["bench"].unique())
    b_idx = {b: i for i, b in enumerate(benches)}
    X_bench = sparse.csr_matrix(
        (np.ones(len(dfa), dtype=np.float32),
         (np.arange(len(dfa)), dfa["bench"].map(b_idx).values)),
        shape=(len(dfa), len(benches)))

    # harness structural features
    def harness_feats(key: str, gold: int) -> list[float]:
        c = legend[key]
        scoring_gen = 1.0 if c["scoring"] == "generation" else 0.0
        fmts = ["letter_plain", "letter_paren", "digit_labels", "instruction",
                "cloze_plain", "cloze_question"]
        fmt_oh = [1.0 if c["fmt"] == f else 0.0 for f in fmts]
        if c.get("perm") is not None:
            perm = c["perm"]
            gp = float(perm.index(gold)) if gold in perm else -1.0
            pi_oh = [1.0 if c["perm_index"] == i else 0.0 for i in range(6)]
            ident = 1.0 if list(perm) == [0, 1, 2, 3] else 0.0
        else:  # loglik configs are order-invariant
            gp, pi_oh, ident = 0.0, [0.0] * 6, 0.0
        return [scoring_gen, *fmt_oh, gp, ident, *pi_oh]

    H = sparse.csr_matrix(np.array(
        [harness_feats(k, g) for k, g in zip(dfa["config"], dfa["gold"])], dtype=np.float32))

    XA = sparse.hstack([X_text, X_bench, X_model, H], format="csr")     # Setting A
    XH = sparse.hstack([X_bench, X_model, H], format="csr")             # harness-only
    XT = sparse.hstack([X_text, X_bench, X_model], format="csr")        # task-only

    margin = dfa["ll_margin"].fillna(0.0).values.astype(np.float32)
    mu, sd = margin.mean(), (margin.std() + 1e-9)
    XAm = sparse.hstack([XA, sparse.csr_matrix(((margin - mu) / sd)[:, None])]).tocsr()  # Setting B

    y_pos = (dfa["delta"] == 1).values.astype(int)
    y_neg = (dfa["delta"] == -1).values.astype(int)
    delta = dfa["delta"].values.astype(int)
    cfg_of_row = dfa["config"].values
    item_of_row = dfa["item_id"].values
    model_of_row = dfa["model"].values
    bc = dfa["baseline_correct"].values.astype(int)
    hc = dfa["correct"].values.astype(int)
    # item-level 80/20 split for tau tuning (fixed by hash, identical across folds)
    val_item = np.array([(stable_item_hash(i) % 10) < 2 for i in item_of_row])

    # saved dense columns for policy evaluation
    print(f"[feat] XA {XA.shape} ({time.time()-t0:.0f}s)")

    def fit_binary(Xtr, ytr, Xte):
        clf = LogisticRegression(C=1.0, max_iter=400, solver="lbfgs")
        clf.fit(Xtr, ytr)
        return clf.predict_proba(Xte)[:, 1]

    def loho(Xmat, tag):
        """Leave-one-harness-out over all 25 non-ref configs. Test predictions are pooled for
        ALL rows; the tune half (20% items, hash-fixed) is used only for tau tuning and
        baseline selection, the eval half (80%) only for reporting."""
        cand = sorted(set(cfg_of_row))
        folds, pooled = [], []
        for j, held in enumerate(cand):
            te = cfg_of_row == held
            tr = ~te
            p_pos = fit_binary(Xmat[tr], y_pos[tr], Xmat[te])
            p_neg = fit_binary(Xmat[tr], y_neg[tr], Xmat[te])
            auc_p = roc_auc_score(y_pos[te], p_pos) if 0 < y_pos[te].sum() < te.sum() else np.nan
            ap_p = average_precision_score(y_pos[te], p_pos) if y_pos[te].sum() else np.nan
            cls = np.argmax(np.stack([p_pos, p_neg, 1 - p_pos - p_neg]), axis=0) - 1
            f1m = f1_score(delta[te], cls, average="macro", labels=[-1, 0, 1])
            folds.append({"held_out": held, "auroc_pos": float(auc_p),
                          "auprc_pos": float(ap_p), "macro_f1_3class": float(f1m),
                          "prev_pos": float(y_pos[te].mean()), "prev_neg": float(y_neg[te].mean())})
            pooled.append(pd.DataFrame({
                "model": model_of_row[te], "item_id": item_of_row[te], "config": held,
                "tune": val_item[te],
                "p_pos": p_pos, "p_neg": p_neg, "baseline_correct": bc[te],
                "harness_correct": hc[te], "delta": delta[te]}))
            if (j + 1) % 5 == 0:
                print(f"  [{tag}] fold {j+1}/{len(cand)} ({time.time()-t0:.0f}s) "
                      f"last AUROC={auc_p:.3f}", flush=True)
        return folds, pd.concat(pooled, ignore_index=True)

    results = {}

    # ---- LOHO: Setting A full (task+model+harness) ----
    print("[loho] Setting A: task + model + harness features", flush=True)
    folds_A, pooled_A = loho(XA, "A")
    results["loho_A"] = folds_A

    # ---- LOHO controls: task-only and harness-only ----
    print("[loho] controls: task-only, harness-only", flush=True)
    folds_T, _ = loho(XT, "T")
    folds_H, _ = loho(XH, "H")
    results["loho_task_only"] = folds_T
    results["loho_harness_only"] = folds_H

    # ---- LOHO: Setting B (A + ll_margin) ----
    print("[loho] Setting B: + ll_margin (after-raw)", flush=True)
    folds_B, pooled_B = loho(XAm, "B")
    results["loho_B_margin"] = folds_B

    # ---- closed-set upper-ish: harness-id one-hot, random-item split ----
    n_cfg = len(cand_configs := sorted(set(cfg_of_row)))
    cid = {c: i for i, c in enumerate(cand_configs)}
    X_id = sparse.hstack([XT, sparse.csr_matrix(
        (np.ones(len(dfa), dtype=np.float32),
         (np.arange(len(dfa)), dfa["config"].map(cid).values)),
        shape=(len(dfa), n_cfg))], format="csr")
    tr_id = ~val_item
    p_id = fit_binary(X_id[tr_id], y_pos[tr_id], X_id[val_item])
    results["closedset_harness_id_auroc"] = float(roc_auc_score(y_pos[val_item], p_id))
    results["closedset_task_only_auroc"] = float(
        roc_auc_score(y_pos[val_item],
                      fit_binary(XT[tr_id], y_pos[tr_id], XT[val_item])))

    def summarize(folds):
        a = pd.DataFrame(folds)
        return {"mean_auroc_pos": float(a["auroc_pos"].mean()),
                "mean_auprc_pos": float(a["auprc_pos"].mean()),
                "mean_macro_f1": float(a["macro_f1_3class"].mean()),
                "min_auroc": float(a["auroc_pos"].min()),
                "max_auroc": float(a["auroc_pos"].max())}

    results["summary"] = {"A_task_model_harness": summarize(folds_A),
                          "task_only": summarize(folds_T),
                          "harness_only": summarize(folds_H),
                          "B_margin": summarize(folds_B)}

    # ------------------------------------------------------- policy metrics
    def policy_eval(pooled: pd.DataFrame, tag: str) -> dict:
        """Out-of-fold predictions: per (model,item) pick argmax value harness among the 25
        candidates; intervene iff max value > tau. tau AND the best-fixed baseline are chosen
        on the tune half only; reported on the eval half."""
        d = pooled.copy()
        d["value"] = d["p_pos"] - d["p_neg"]
        tune, ev = d[d["tune"]], d[~d["tune"]]
        # best fixed baseline: argmax config accuracy on tune half (never sees eval half)
        tune_acc = tune.groupby("config")["harness_correct"].mean()
        best_train_cfg = tune_acc.idxmax()  # ref not in pooled (excluded from delta rows)
        # tau on tune half: per (model,item) pick best value config
        vr = tune.loc[tune.groupby(["model", "item_id"])["value"].idxmax()]
        best_tau, best_acc_tau = 0.2, -1.0
        for tau in TAU_GRID:
            use_v = (vr["value"] > tau).values
            acc = float(np.where(use_v, vr["harness_correct"].values,
                                 vr["baseline_correct"].values).mean())
            if acc > best_acc_tau:
                best_acc_tau, best_tau = acc, float(tau)
        # apply on eval half
        br = ev.loc[ev.groupby(["model", "item_id"])["value"].idxmax()]
        use = (br["value"] > best_tau).values
        final = np.where(use, br["harness_correct"].values, br["baseline_correct"].values)
        base_acc_eval = float(ev.groupby(["model", "item_id"])["baseline_correct"].first().mean())
        bestfixed_eval = float(ev[ev["config"] == best_train_cfg]["harness_correct"].mean())
        return {
            "tau": best_tau,
            "best_fixed_config": best_train_cfg,
            "baseline_H0_acc": base_acc_eval,
            "best_fixed_acc": bestfixed_eval,
            "policy_acc": float(final.mean()),
            "policy_gain_vs_H0_pp": 100 * (float(final.mean()) - base_acc_eval),
            "policy_gain_vs_best_fixed_pp": 100 * (float(final.mean()) - bestfixed_eval),
            "intervention_rate": float(use.mean()),
            "harm_rate_on_intervention": float((br["delta"].values[use] == -1).mean()) if use.any() else 0.0,
            "repair_rate_on_intervention": float((br["delta"].values[use] == 1).mean()) if use.any() else 0.0,
            "oracle_acc": float(ev.groupby(["model", "item_id"]).apply(
                lambda x: max(x["harness_correct"].max(), x["baseline_correct"].max()),
                include_groups=False).mean()),
        }

    results["policy_setting_A"] = policy_eval(pooled_A, "A_task_model_harness")
    results["policy_setting_B"] = policy_eval(pooled_B, "B_margin")

    # bootstrap CI on policy gain vs best fixed (eval half only, item-level bootstrap)
    pa = results["policy_setting_A"]
    d = pooled_A.copy()
    d["value"] = d["p_pos"] - d["p_neg"]
    ev = d[~d["tune"]]
    chosen = ev.groupby(["model", "item_id"])["value"].idxmax()
    br = ev.loc[chosen]
    use = (br["value"] > pa["tau"]).values
    final = pd.Series(np.where(use, br["harness_correct"].values, br["baseline_correct"].values),
                      index=br.set_index(["model", "item_id"]).index)
    bf = ev[ev["config"] == pa["best_fixed_config"]].set_index(["model", "item_id"])["harness_correct"]
    rng = np.random.default_rng(SEED)
    items_u = final.index.get_level_values("item_id").unique()
    gains = []
    for _ in range(500):
        samp = rng.choice(items_u, size=len(items_u), replace=True)
        a = np.concatenate([final.xs(s, level=1).values for s in samp])
        b = np.concatenate([bf.xs(s, level=1).values for s in samp])
        gains.append(a.mean() - b.mean())
    results["policy_setting_A"]["gain_vs_best_fixed_ci95"] = [
        float(np.percentile(gains, 2.5)), float(np.percentile(gains, 97.5))]

    # ----------------------------------------------------------------- save
    dfa_out = dfa[["bench", "item_id", "model", "config", "correct", "baseline_correct",
                   "delta", "ll_margin"]].copy()
    dfa_out.rename(columns={"bench": "dataset", "config": "harness_id",
                            "correct": "harness_correct"}, inplace=True)
    dfa_out["baseline_harness_id"] = ref
    dfa_out.insert(0, "domain", "mcq_harness_config")
    dfa_out.to_parquet(OUT / "outcome_matrix.parquet", index=False)

    (OUT / "day0_stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    (OUT / "loho_results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results["summary"], indent=2))
    print(json.dumps(results["policy_setting_A"], indent=2))
    print(f"[done] {time.time()-t0:.0f}s total")


if __name__ == "__main__":
    main()
