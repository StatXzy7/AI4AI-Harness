"""Phase-II outcome collector.

Differences from experiment/tthe_collector.py that matter for the confirmatory run:

  * DUAL SCORING     every cell carries both the BIRD-official verdict (primary) and the
                     legacy in-loop verdict (secondary). Phase-I could not do this
                     retroactively because the main matrix predates final_sql logging.
  * RESUMABLE        results append to JSONL keyed on (target, harness, task); re-running
                     skips finished cells. A 1169-task x 40-harness run takes hours and
                     must survive an interrupted connection.
  * CACHE CONTROL    --no-cache bypasses the shared solver cache so the cache's effect on
                     measured diversity can be quantified rather than asserted (freeze R2).
  * REPEATS          --repeat N tags each pass so solver stochasticity can be separated
                     from task-sampling uncertainty (freeze R3).
  * db_id RETAINED   every row keeps its database, for leave-one-database-out routing.

Usage:
    export PARATERA_API_KEY=...
    PYTHONPATH=. python phase2/collect.py \
        --split split_p2_test_core --harnesses bare,hpc_repair \
        --target GLM-5.3-Flash --workers 32 --out artifacts/phase2/run_core.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TTHE = ROOT / "external" / "TTHE"
sys.path.insert(0, str(TTHE))
sys.path.insert(0, str(ROOT / "experiment"))

BASELINE = "bare"


def load_done(path: Path) -> set[tuple]:
    done = set()
    if not path.exists():
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue  # a half-written final line from a killed run
            done.add((r["target"], r["harness_id"], r["task_id"], r.get("repeat", 0)))
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True, help="file under experiment/phase2/, e.g. split_p2_test")
    ap.add_argument("--harnesses", required=True, help="'all' or comma-separated harness names")
    ap.add_argument("--exclude", default="")
    ap.add_argument("--target", required=True, help="frozen target model id")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--repeat", type=int, default=0, help="repeat index, tags rows (freeze R3)")
    ap.add_argument("--no-cache", action="store_true", help="bypass the shared solver cache (freeze R2)")
    ap.add_argument("--limit", type=int, default=0, help="debug: cap tasks per database")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    # the target must be fixed before bridge is imported -- bridge builds its client at import
    os.environ["SOLVER_MODEL"] = a.target
    if a.no_cache:
        # a per-run cache file keeps the shared cache clean; it is then bypassed outright below
        os.environ["SQL_SOLVER_CACHE"] = str(ROOT / "artifacts" / "phase2" / f".nocache_{a.repeat}.json")

    from text_to_sql import bridge
    from text_to_sql.evolve import AGENTS_DIR, load_harness

    from phase2.official_scorer import _fetch, gold_sql_map

    if a.no_cache:
        bridge._CACHE.get_or_call = lambda parts, produce: produce()
        print("[collect] solver cache BYPASSED")

    out = Path(a.out)
    out = out if out.is_absolute() else ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(out)
    print(f"[collect] {len(done)} cells already recorded in {out.name}")

    split = json.loads((ROOT / "experiment" / "phase2" / f"{a.split}.json").read_text())
    by_db = split["by_db"]
    if a.limit:
        by_db = {d: idxs[: a.limit] for d, idxs in by_db.items()}

    golds = gold_sql_map()
    dbs, qmap, gold_legacy, gold_official = {}, {}, {}, {}
    for d in by_db:
        dbs[d] = bridge.get_db(d)
        qmap[d] = bridge.eval_questions(d)
    tasks = [(d, i) for d, idxs in by_db.items() for i in idxs]
    # gold executed once per task, under both judges
    for d, i in tasks:
        tid = f"{d}#{i}"
        gold_legacy[tid] = bridge.gold_result(dbs[d], qmap[d][i].gold_sql)
        gold_official[tid] = _fetch(d, golds[tid])
    print(f"[collect] {len(tasks)} tasks over {len(by_db)} databases | target={a.target}")

    if a.harnesses == "all":
        names = sorted(p.stem for p in AGENTS_DIR.glob("*.py") if p.stem != "__init__")
    else:
        names = [s.strip() for s in a.harnesses.split(",") if s.strip()]
    skip = {s.strip() for s in a.exclude.split(",") if s.strip()}
    names = [n for n in names if n not in skip]

    lock = threading.Lock()
    fh = open(out, "a", encoding="utf-8")

    for name in names:
        src = (AGENTS_DIR / f"{name}.py")
        try:
            code = src.read_text(encoding="utf-8")
            harness_by_db = {d: load_harness(name, dbs[d]) for d in by_db}
        except Exception as e:
            print(f"  [skip] {name}: uncallable -- {e!r}")
            continue
        chash = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]

        todo = [t for t in tasks if (a.target, name, f"{t[0]}#{t[1]}", a.repeat) not in done]
        if not todo:
            print(f"  [have] {name}: complete")
            continue

        def solve_one(ti):
            d, qi = ti
            tid = f"{d}#{qi}"
            # ONE HARNESS INSTANCE PER TASK. SQLHarness carries mutable per-solve state
            # (_trace, _call_seq); sharing an instance across worker threads corrupts the
            # trace counts and, worse, the cache `seq` numbers that make deliberate
            # resampling work.
            h = load_harness(name, dbs[d])
            t0 = time.time()
            try:
                sql = h.solve(qmap[d][qi].question) or ""
                err = None
            except Exception as e:
                sql, err = "", repr(e)[:300]
            ms = int((time.time() - t0) * 1000)

            legacy = 0
            if sql.strip():
                res = bridge.execute(h.db, sql)
                legacy = int(bridge.is_correct(res, gold_legacy[tid]))
            pred = _fetch(d, sql)
            g = gold_official[tid]
            official = int(pred is not None and g is not None and set(pred) == set(g))

            return {
                "target": a.target, "harness_id": name, "task_id": tid, "db_id": d,
                "repeat": a.repeat, "no_cache": bool(a.no_cache),
                "official_correct": official, "legacy_correct": legacy,
                "final_sql": sql[:4000], "n_llm_calls": sum(
                    1 for s in getattr(h, "_trace", []) if s.get("step") == "coder_llm"),
                "n_execs": sum(1 for s in getattr(h, "_trace", []) if s.get("step") == "execute_sql"),
                "latency_ms": ms, "code_hash": chash, "error": err,
            }

        n_ok = 0
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            for k, rec in enumerate(ex.map(solve_one, todo)):
                with lock:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    if k % 50 == 0:
                        fh.flush()
                n_ok += rec["official_correct"]
                if (k + 1) % 100 == 0:
                    print(f"    {name}: {k+1}/{len(todo)} acc={n_ok/(k+1):.3f}", flush=True)
        fh.flush()
        print(f"  [done] {name}: official_acc={n_ok/len(todo):.3f} on {len(todo)} new cells", flush=True)

    fh.close()
    try:
        bridge._CACHE.flush()
    except Exception:
        pass
    print(f"[collect] wrote {out}")


if __name__ == "__main__":
    main()
