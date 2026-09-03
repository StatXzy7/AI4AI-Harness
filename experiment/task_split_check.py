"""Task-held-out value-prediction control on the admitted D6 population (v2, stratified).

Round-4 review required stratified random splits, multiple seeds, harness features, and
per-seed AUROCs. Protocol: within the D6 outcome matrix (bare + 6 DeepSeek-gated
harnesses, 151 tasks), for each of 5 seeds take a random database-stratified 50% of
tasks as train and the rest as test; logistic head on task TF-IDF + harness one-hot
features; report repair (delta=+1) AUROC and an argmax-p policy (threshold 0.5) vs
bare on unseen tasks.

Output: artifacts/day2/task_split_D6_v2.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
SEEDS = [1234, 2, 3, 4, 5]

df = pd.read_parquet(ROOT / "artifacts" / "day2" / "eval151_sub_D6.parquet")
dfa = df[df.harness_id != "bare"].copy()
dfa["delta"] = dfa["harness_correct"] - dfa["baseline_correct"]
tasks = pd.Series(sorted(dfa.task_id.unique()))
dbs = tasks.str.split("#").str[0]

tfv = TfidfVectorizer(max_features=256, ngram_range=(1, 2), min_df=2, sublinear_tf=True)
Xt = tfv.fit_transform(dfa.task_text.fillna(""))
hids = dfa.harness_id.astype("category")
Xh = sp.csr_matrix((np.ones(len(dfa)), (np.arange(len(dfa)), hids.cat.codes)),
                   shape=(len(dfa), hids.cat.categories.size))
X = sp.hstack([Xt, Xh], format="csr")
yp = (dfa.delta == 1).astype(int).values


def run_split(seed: int):
    rng = np.random.default_rng(seed)
    tr_tasks = set()
    for db in dbs.unique():
        t_db = tasks[dbs == db].tolist()
        tr_tasks |= set(rng.choice(t_db, size=len(t_db) // 2, replace=False))
    tr = dfa.task_id.isin(tr_tasks).values
    clf = SGDClassifier(loss="log_loss", alpha=1e-5, max_iter=30, random_state=seed)
    clf.fit(X[tr], yp[tr])
    p = clf.predict_proba(X[~tr])[:, 1]
    auc = roc_auc_score(yp[~tr], p) if 0 < yp[~tr].sum() < (~tr).sum() else float("nan")
    d = dfa[~tr].copy()
    d["p"] = p
    best = d.loc[d.groupby("task_id")["p"].idxmax()]
    acc_pol = float(np.where(best.p > 0.5, best.harness_correct, best.baseline_correct).mean())
    acc_bare = float(d.groupby("task_id").baseline_correct.first().mean())
    return {"seed": seed, "train_tasks": sorted(tr_tasks), "auroc": round(float(auc), 4),
            "policy_acc": round(acc_pol, 4), "bare_acc": round(acc_bare, 4)}


rows = [run_split(s) for s in SEEDS]
out = {
    "protocol": "stratified task-held-out control on D6: random database-stratified 50% tasks "
                "per seed in train, rest as test; task TF-IDF + harness one-hot features; "
                "SGD logistic (alpha=1e-5, max_iter=30); repair=delta==+1",
    "seeds": rows,
    "auroc_repair_unseen_tasks_mean": round(float(np.mean([r["auroc"] for r in rows])), 4),
    "auroc_seed_range": [round(min(r["auroc"] for r in rows), 4), round(max(r["auroc"] for r in rows), 4)],
    "policy_acc_mean": round(float(np.mean([r["policy_acc"] for r in rows])), 4),
    "bare_acc_mean": round(float(np.mean([r["bare_acc"] for r in rows])), 4),
    "policy_minus_bare_pp": round(100 * (float(np.mean([r["policy_acc"] for r in rows])) -
                                         float(np.mean([r["bare_acc"] for r in rows]))), 2),
}
(ROOT / "artifacts" / "day2" / "task_split_D6_v2.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
