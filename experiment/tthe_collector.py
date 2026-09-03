"""TTHE outcome collector — builds the unified per-item outcome matrix over a harness POPULATION.

Unlike TTHE's optimize loop (which commits ONE winning harness), we keep every candidate
(seed + cand_*) and evaluate each on every task, recording per-item correctness. This is the
raw material for harness value prediction.

Run from TTHE repo root (or set TTHE_ROOT):
    PYTHONPATH=. python ../experiment/tthe_collector.py --db demo --limit 10 --out ../artifacts/outcomes/tthe_smoke.parquet

Schema (PROBLEM_FREEZE.md section 10):
    dataset, domain, task_id, model_id, harness_id, baseline_harness_id,
    baseline_correct, harness_correct, delta, task_text, harness_text, harness_description,
    prompt_tokens, completion_tokens, latency_ms, cost_usd, split
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import sys
import time
from pathlib import Path

TTHE_ROOT = Path(__file__).resolve().parent.parent / "external" / "TTHE"
sys.path.insert(0, str(TTHE_ROOT))

import pandas as pd  # noqa: E402

from text_to_sql import bridge  # noqa: E402
from text_to_sql.evolve import AGENTS_DIR, load_harness  # noqa: E402

BASELINE = "bare"


def code_hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def harness_description(p: Path) -> str:
    """First docstring line(s) of the harness module, else first comment block."""
    src = p.read_text(encoding="utf-8")
    m = re.search(r'"""(.{0,600}?)"""', src, re.S)
    if m:
        return " ".join(m.group(1).split())[:400]
    return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="demo")
    ap.add_argument("--harnesses", default="all", help="'all' or comma-separated names")
    ap.add_argument("--exclude", default="", help="comma-separated names to skip")
    ap.add_argument("--limit", type=int, default=10, help="number of eval questions")
    ap.add_argument("--model-tag", default=None, help="override model_id in records")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--split", default=None, help="experiment/split_*.json with by_db")
    ap.add_argument("--out", default="artifacts/outcomes/tthe_smoke.parquet")
    args = ap.parse_args()

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path(__file__).resolve().parent.parent / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cfg_text = (TTHE_ROOT / "config.yaml").read_text()
    m_solver = re.search(r"solver_model:\s*(\S+)", cfg_text)
    solver_model = args.model_tag or (m_solver.group(1) if m_solver else "unknown")

    if args.split:
        split = json.loads((Path(__file__).resolve().parent.parent / "experiment" / args.split).read_text())
        by_db = split["by_db"]
    else:
        by_db = {args.db: list(range(min(args.limit, len(bridge.eval_questions(args.db)))))}
    # tasks: list of (db_id, local_idx); per-db harness instances
    tasks = [(d, i) for d, idxs in by_db.items() for i in idxs]
    dbs, qmap, gmap = {}, {}, {}
    for d in by_db:
        dbs[d] = bridge.get_db(d)
        qs = bridge.eval_questions(d)
        qmap[d] = qs
        gmap[d] = [bridge.gold_result(dbs[d], q.gold_sql) for q in qs]
    print(f"[collector] split tasks: { {d: len(v) for d, v in by_db.items()} }")

    if args.harnesses == "all":
        names = sorted(p.stem for p in AGENTS_DIR.glob("*.py") if p.stem != "__init__")
    else:
        names = [s.strip() for s in args.harnesses.split(",")]
    skip = {s.strip() for s in args.exclude.split(",") if s.strip()}
    names = [n for n in names if n not in skip]
    print(f"[collector] tasks={ {d: len(v) for d, v in by_db.items()} } | harnesses: {names}")

    rows, registry = [], []
    for name in names:
        harness_by_db = {d: load_harness(name, dbs[d]) for d in by_db}
        p = AGENTS_DIR / f"{name}.py"
        desc = harness_description(p)
        registry.append({
            "harness_id": name, "code_path": str(p), "code_hash": code_hash(p),
            "description": desc, "parent_id": None, "builder_role": "tthe_candidate",
            "generation_round": 0})
        try:
            for d in by_db:
                load_harness(name, dbs[d])  # import check per db
        except Exception as e:
            print(f"  [skip] {name}: {e!r}")
            continue

        def solve_one(ti):
            d, qi = ti
            harness = harness_by_db[d]
            q = qmap[d][qi]
            gold = gmap[d][qi]
            t0 = time.time()
            try:
                sql = harness.solve(q.question)
                err = None
            except Exception as e:
                sql, err = "", repr(e)
            latency_ms = int((time.time() - t0) * 1000)
            res = bridge.execute(harness.db, sql) if sql.strip() else {"ok": False, "rows": []}
            correct = int(bridge.is_correct(res, gold)) if sql.strip() else 0
            return {
                "dataset": d, "domain": "text_to_sql", "task_id": f"{d}#{qi}",
                "model_id": solver_model, "harness_id": name,
                "baseline_harness_id": BASELINE,
                "baseline_correct": None,  # filled after pass
                "harness_correct": correct, "delta": None,
                "task_text": q.question, "harness_text": p.read_text(encoding="utf-8"),
                "harness_description": desc,
                "final_sql": sql,
                "prompt_tokens": None, "completion_tokens": None,
                "latency_ms": latency_ms, "cost_usd": None,
                "split": "unassigned", "error": err}

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(solve_one, ti) for ti in tasks]
            for k, f in enumerate(futs):
                rows.append(f.result())
                if (k + 1) % 25 == 0:
                    print(f"    {name}: {k+1}/{len(tasks)}", flush=True)
        acc = sum(r["harness_correct"] for r in rows if r["harness_id"] == name) / max(1, len(tasks))
        print(f"  [done] {name}: acc={acc:.3f} ({len(tasks)} tasks)", flush=True)

    df = pd.DataFrame(rows)
    # fill baseline correctness + delta
    bare_acc = df[df["harness_id"] == BASELINE].set_index("task_id")["harness_correct"]
    if BASELINE not in set(df["harness_id"]):
        raise SystemExit("baseline harness 'bare' missing from population")
    df["baseline_correct"] = df["task_id"].map(bare_acc)
    df["delta"] = df["harness_correct"] - df["baseline_correct"]
    df.to_parquet(out_path, index=False)

    reg_path = out_path.parent / "harness_registry.jsonl"
    with open(reg_path, "a", encoding="utf-8") as f:
        for r in registry:
            f.write(json.dumps(r) + "\n")

    piv = df.pivot_table(index="task_id", columns="harness_id", values="harness_correct")
    print(f"[collector] wrote {out_path} ({len(df)} rows, {df['harness_id'].nunique()} harnesses)")
    print(f"[collector] harness registry appended -> {reg_path}")
    print("[collector] per-harness accuracy:")
    print(df.groupby("harness_id")["harness_correct"].mean().round(3).to_string())
    if len(piv.columns) > 1 and BASELINE in piv.columns:
        union = piv.drop(columns=[BASELINE]).max(axis=1)
        print(f"[collector] best-fixed acc = {piv.max().mean():.3f} | "
              f"oracle-any acc = {pd.concat([union, piv[BASELINE]], axis=1).max(axis=1).mean():.3f}")


if __name__ == "__main__":
    main()
