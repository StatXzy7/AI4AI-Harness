"""Task-held-out value-prediction control on the admitted D6 population.

Round-2 review (P0-3 follow-up) required a machine-readable record of the task-level
split test reported in paper §6.1. Protocol: within the D6 outcome matrix (bare + 6
DeepSeek-gated harnesses, 151 tasks), train logistic heads on the FIRST 76 tasks
(sorted task_id) and evaluate repair (delta=+1) AUROC and a simple argmax-p policy
(threshold 0.5) on the remaining 75 unseen tasks. Deterministic; seed fixed.

Output: artifacts/day2/task_split_D6.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
SEED = 1234
N_TRAIN_TASKS = 76

df = pd.read_parquet(ROOT / "artifacts" / "day2" / "eval151_sub_D6.parquet")
dfa = df[df.harness_id != "bare"].copy()
dfa["delta"] = dfa["harness_correct"] - dfa["baseline_correct"]
tasks = sorted(dfa.task_id.unique())
tr_tasks = set(tasks[:N_TRAIN_TASKS])
tr = dfa.task_id.isin(tr_tasks).values

tfv = TfidfVectorizer(max_features=256, ngram_range=(1, 2), min_df=2, sublinear_tf=True)
X = tfv.fit_transform(dfa.task_text.fillna(""))
yp = (dfa.delta == 1).astype(int).values

clf = SGDClassifier(loss="log_loss", alpha=1e-5, max_iter=30, random_state=SEED)
clf.fit(X[tr], yp[tr])
p = clf.predict_proba(X[~tr])[:, 1]
auroc = float(roc_auc_score(yp[~tr], p))

d = dfa[~tr].copy()
d["p"] = p
best = d.loc[d.groupby("task_id")["p"].idxmax()]
acc_policy = float(np.where(best.p > 0.5, best.harness_correct, best.baseline_correct).mean())
acc_bare = float(d.groupby("task_id").baseline_correct.first().mean())
tr_acc = dfa[tr].groupby("harness_id").harness_correct.mean()
besth = str(tr_acc.idxmax())
acc_bf = float(d[d.harness_id == besth].groupby("task_id").harness_correct.first().mean())
oracle = float(pd.concat([dfa[~tr].groupby("task_id").harness_correct.max(),
                          dfa[~tr].groupby("task_id").baseline_correct.max()], axis=1).max(axis=1).mean())

out = {
    "protocol": "task-held-out control; train on first 76 sorted task_ids, test on remaining 75 (D6 population)",
    "seed": SEED, "n_train_tasks": N_TRAIN_TASKS, "n_test_tasks": len(tasks) - N_TRAIN_TASKS,
    "test_task_ids": sorted(set(tasks) - tr_tasks),
    "auroc_repair_on_unseen_tasks": round(auroc, 4),
    "test_positive_rate": round(float(yp[~tr].mean()), 4),
    "policy_acc_unseen": round(acc_policy, 4),
    "bare_acc_unseen": round(acc_bare, 4),
    "best_fixed_on_train": besth,
    "best_fixed_acc_unseen": round(acc_bf, 4),
    "oracle_acc_unseen": round(oracle, 4),
}
(ROOT / "artifacts" / "day2" / "task_split_D6.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
