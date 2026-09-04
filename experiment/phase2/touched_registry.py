"""Phase-II contamination registry.

Scans every artifact this project ever produced and records which BIRD dev questions
were OBSERVED (outcome or trace seen by a human or used to develop the protocol).
Any question in the touched set is BANNED from the Phase-II confirmatory test.

Output: artifacts/phase2/touched_items.json
    {"touched": {db_id: [local_idx, ...]}, "touched_qids": [global question_id, ...],
     "sources": {source_name: n_items}}

task_id convention (experiment/tthe_collector.py): f"{db_id}#{local_idx}" where local_idx
indexes ase.dataset.BirdDataset.eval_questions(db_id) — i.e. dev.json order filtered by db_id.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIRD_DEV = ROOT / "external" / "data" / "bird" / "dev_20240627" / "dev.json"
OUT = ROOT / "artifacts" / "phase2" / "touched_items.json"


def local_index_map() -> dict[str, list[int]]:
    """db_id -> list of global question_id, ordered exactly as eval_questions() yields them."""
    dev = json.loads(BIRD_DEV.read_text(encoding="utf-8"))
    by_db: dict[str, list[int]] = defaultdict(list)
    for e in dev:
        by_db[e["db_id"]].append(e["question_id"])
    return dict(by_db)


def scan() -> tuple[dict[str, set[int]], dict[str, int]]:
    touched: dict[str, set[int]] = defaultdict(set)
    sources: dict[str, int] = {}

    # 1. explicit split files — every question named in one was selected/inspected
    for p in sorted((ROOT / "experiment").glob("split_*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        n = 0
        for db, idxs in (d.get("by_db") or {}).items():
            for i in idxs:
                touched[db].add(int(i))
                n += 1
        # split_card_games.json carries bare build_ids/eval_ids against card_games
        if not d.get("by_db"):
            for key in ("build_ids", "eval_ids"):
                for i in d.get(key) or []:
                    touched["card_games"].add(int(i))
                    n += 1
        sources[p.name] = n

    # 2. outcome matrices — every task_id present had its correctness observed
    import pandas as pd

    for p in sorted((ROOT / "artifacts" / "outcomes").glob("*.parquet")):
        try:
            df = pd.read_parquet(p, columns=["task_id"])
        except Exception:
            continue
        n = 0
        for tid in df["task_id"].unique():
            if "#" not in str(tid):
                continue
            db, _, idx = str(tid).rpartition("#")
            if idx.isdigit():
                touched[db].add(int(idx))
                n += 1
        sources[p.name] = n

    # 3. day-1/day-2 result JSON blobs that embed task_ids
    for p in sorted(ROOT.glob("artifacts/day*/**/*.json")):
        try:
            raw = p.read_text(encoding="utf-8")
        except Exception:
            continue
        n = 0
        import re

        for m in re.finditer(r'"([a-z_0-9]+)#(\d+)"', raw):
            touched[m.group(1)].add(int(m.group(2)))
            n += 1
        if n:
            sources[str(p.relative_to(ROOT))] = n

    return touched, sources


def main() -> None:
    idx_map = local_index_map()
    touched, sources = scan()

    # drop anything that is not a real (db, local_idx) pair
    clean: dict[str, list[int]] = {}
    qids: list[int] = []
    for db, idxs in sorted(touched.items()):
        if db not in idx_map:
            continue
        keep = sorted(i for i in idxs if 0 <= i < len(idx_map[db]))
        if keep:
            clean[db] = keep
            qids.extend(idx_map[db][i] for i in keep)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"touched": clean, "touched_qids": sorted(qids), "sources": sources},
            indent=2,
        ),
        encoding="utf-8",
    )

    total_by_db = {db: len(v) for db, v in idx_map.items()}
    print(f"[registry] BIRD dev: {sum(total_by_db.values())} questions / {len(total_by_db)} databases")
    print("[registry] touched per database:")
    for db in sorted(total_by_db):
        t = len(clean.get(db, []))
        print(f"    {db:28s} touched {t:4d} / {total_by_db[db]:4d}")
    print(f"[registry] TOTAL touched = {len(qids)}  ->  untouched pool = {sum(total_by_db.values()) - len(qids)}")
    print(f"[registry] wrote {OUT}")


if __name__ == "__main__":
    main()
