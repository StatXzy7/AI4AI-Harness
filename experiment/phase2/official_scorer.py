"""BIRD official execution-accuracy scorer, and offline re-scoring of logged runs.

The official BIRD `evaluation.py` judges a prediction as:

    conn = sqlite3.connect(db_path); cur = conn.cursor()
    cur.execute(predicted_sql);    predicted_res    = cur.fetchall()
    cur.execute(ground_truth_sql); ground_truth_res = cur.fetchall()
    res = 1 if set(predicted_res) == set(ground_truth_res) else 0

wrapped in func_timeout(30s); any exception or timeout scores 0. Note it compares sets of RAW
tuples -- no string coercion, no row cap.

This project's in-loop judge (ase.db.compare_results) instead compares
{tuple(str(cell) for cell in row)} under a 20000-row cap. The two disagree in both directions:

    official  looser  on numeric type:  {(1,)} == {(1.0,)}        -> official 1, ours 0
    official stricter on str/num:       {('1',)} vs {(1,)}        -> official 0, ours 1
    official  looser  on huge results:  >20000 rows               -> ours truncates

Because the collector logs `final_sql`, every historical run can be re-judged offline with no
new API calls. That is what `rescore` does.

Usage:
    python experiment/phase2/official_scorer.py rescore \
        --parquet artifacts/outcomes/tthe_eval151_matrix_round4.parquet \
        --out artifacts/phase2/rescore_eval151.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIRD_ROOT = ROOT / "external" / "data" / "bird" / "dev_20240627"
DB_DIR = BIRD_ROOT / "dev_databases"
TIMEOUT_S = 30.0


def _db_path(db_id: str) -> Path:
    return DB_DIR / db_id / f"{db_id}.sqlite"


def _fetch(db_id: str, sql: str):
    """Run SQL as the official scorer does, under a real wall-clock limit. Returns None on failure.

    sqlite3's `timeout=` only bounds waiting for a LOCK, not execution, so a generated query with a
    runaway join will otherwise hang a worker forever. set_progress_handler fires every N VM steps
    and aborts the statement when it returns non-zero, which is the only in-process way to interrupt
    a long-running SQLite query.
    """
    if not (sql or "").strip():
        return None
    conn = None
    try:
        conn = sqlite3.connect(str(_db_path(db_id)), timeout=TIMEOUT_S)
        conn.text_factory = lambda b: b.decode("utf-8", "ignore")
        deadline = time.monotonic() + TIMEOUT_S
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
        cur = conn.cursor()
        cur.execute(sql)
        return cur.fetchall()
    except Exception:
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def official_correct(db_id: str, predicted_sql: str, gold_sql: str) -> int:
    pred = _fetch(db_id, predicted_sql)
    gold = _fetch(db_id, gold_sql)
    if pred is None or gold is None:
        return 0
    return int(set(pred) == set(gold))


def gold_sql_map() -> dict[str, str]:
    """task_id ('db#local_idx') -> gold SQL, using the eval_questions() ordering contract."""
    dev = json.loads((BIRD_ROOT / "dev.json").read_text(encoding="utf-8"))
    per_db: dict[str, int] = {}
    out: dict[str, str] = {}
    for e in dev:
        db = e["db_id"]
        i = per_db.get(db, 0)
        per_db[db] = i + 1
        out[f"{db}#{i}"] = e.get("SQL") or e.get("query") or ""
    return out


def rescore(parquet: Path, out: Path, workers: int) -> None:
    import pandas as pd

    df = pd.read_parquet(parquet)
    if "final_sql" not in df.columns:
        raise SystemExit(f"{parquet.name} has no final_sql column -- cannot re-score offline")
    golds = gold_sql_map()

    rows = df[["task_id", "harness_id", "harness_correct", "final_sql"]].to_dict("records")
    unresolved = [r for r in rows if r["task_id"] not in golds]
    if unresolved:
        raise SystemExit(f"{len(unresolved)} task_ids not found in dev.json, e.g. {unresolved[0]['task_id']}")

    def judge(r):
        db = str(r["task_id"]).rpartition("#")[0]
        pred = _fetch(db, r["final_sql"])
        gold = gold_rows.get(r["task_id"])
        if pred is None or gold is None:
            return 0
        return int(set(pred) == set(gold))

    # gold SQL is identical across every harness row for a task -- execute each gold exactly once
    task_dbs = {t: str(t).rpartition("#")[0] for t in df["task_id"].unique()}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        gold_rows = dict(
            zip(task_dbs, ex.map(lambda t: _fetch(task_dbs[t], golds[t]), task_dbs))
        )
    n_gold_fail = sum(1 for v in gold_rows.values() if v is None)
    if n_gold_fail:
        print(f"[official] warning: {n_gold_fail} gold queries failed to execute")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        official = list(ex.map(judge, rows))

    df = df.assign(official_correct=official)
    agree = int((df["official_correct"] == df["harness_correct"]).sum())
    n = len(df)

    per_h = (
        df.groupby("harness_id")[["harness_correct", "official_correct"]]
        .mean()
        .round(4)
        .sort_index()
    )
    flips = df[df["official_correct"] != df["harness_correct"]]
    summary = {
        "parquet": str(parquet.relative_to(ROOT)),
        "n_cells": n,
        "agreement": round(agree / n, 4),
        "n_disagree": n - agree,
        "ours_1_official_0": int(((df["harness_correct"] == 1) & (df["official_correct"] == 0)).sum()),
        "ours_0_official_1": int(((df["harness_correct"] == 0) & (df["official_correct"] == 1)).sum()),
        "mean_acc_ours": round(float(df["harness_correct"].mean()), 4),
        "mean_acc_official": round(float(df["official_correct"].mean()), 4),
        "per_harness": per_h.to_dict("index"),
        "disagreeing_tasks": sorted(flips["task_id"].unique().tolist())[:100],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    df.to_parquet(out.with_suffix(".parquet"), index=False)

    print(f"[official] {parquet.name}: {n} cells, judge agreement {agree/n:.4f} ({n-agree} disagree)")
    print(f"[official] mean acc  ours {df['harness_correct'].mean():.4f} -> official {df['official_correct'].mean():.4f}")
    print(f"[official] ours=1/official=0: {summary['ours_1_official_0']} | "
          f"ours=0/official=1: {summary['ours_0_official_1']}")
    print(f"[official] wrote {out} (+ .parquet with official_correct column)")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rescore")
    r.add_argument("--parquet", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    if a.cmd == "rescore":
        p = Path(a.parquet)
        o = Path(a.out)
        rescore(p if p.is_absolute() else ROOT / p, o if o.is_absolute() else ROOT / o, a.workers)


if __name__ == "__main__":
    main()
