"""Phase-II split construction. Run ONCE, before any confirmatory outcome is observed.

Design rule (stricter than item-level holdout): a database is admissible for the confirmatory
test only if NO question in it was ever observed. Protocol development read card_games and
formula_1 schemas, traces and outcomes, so BOTH databases are banned wholesale -- including the
52 formula_1 items the registry marks untouched.

    DEV        card_games + formula_1            (365 q)  builder-visible, gate/threshold tuning
    TEST       the 9 never-opened databases     (1169 q)  frozen confirmatory evaluation
    TEST_CORE  stratified subsample of TEST      (~400 q) wide sweeps (many harnesses)

TEST_CORE is drawn HERE, before any outcome exists, with a fixed seed, so using it later is not
a post-hoc selection. Database identity is retained on every item so routing can be evaluated
with leave-one-database-out grouping.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIRD_DEV = ROOT / "external" / "data" / "bird" / "dev_20240627" / "dev.json"
TOUCHED = ROOT / "artifacts" / "phase2" / "touched_items.json"
OUTDIR = ROOT / "experiment" / "phase2"

BANNED_DBS = {"card_games", "formula_1"}
CORE_SIZE = 400
SEED = 20260904


def main() -> None:
    dev = json.loads(BIRD_DEV.read_text(encoding="utf-8"))
    touched = json.loads(TOUCHED.read_text(encoding="utf-8"))

    by_db: dict[str, list[dict]] = defaultdict(list)
    for e in dev:
        by_db[e["db_id"]].append(e)

    # local_idx is the position within the db-filtered dev.json order (eval_questions contract)
    dev_split: dict[str, list[int]] = {}
    test_split: dict[str, list[int]] = {}
    for db, entries in sorted(by_db.items()):
        idxs = list(range(len(entries)))
        if db in BANNED_DBS:
            dev_split[db] = idxs
        else:
            assert not touched["touched"].get(db), f"{db} was supposed to be untouched"
            test_split[db] = idxs

    # stratified core subsample: proportional allocation, fixed seed, sorted for stability
    rng = random.Random(SEED)
    total = sum(len(v) for v in test_split.values())
    core: dict[str, list[int]] = {}
    for db, idxs in sorted(test_split.items()):
        k = max(1, round(CORE_SIZE * len(idxs) / total))
        core[db] = sorted(rng.sample(idxs, min(k, len(idxs))))

    meta = {
        "created": "2026-09-04",
        "seed": SEED,
        "rule": "database-level holdout; card_games+formula_1 banned wholesale as protocol-development databases",
        "banned_dbs": sorted(BANNED_DBS),
    }
    for name, by, note in [
        ("split_p2_dev", dev_split, "contaminated development pool (builder-visible, gate/threshold tuning)"),
        ("split_p2_test", test_split, "FROZEN confirmatory test: 9 never-opened databases"),
        ("split_p2_test_core", core, f"stratified {CORE_SIZE}-item subsample of split_p2_test, drawn pre-outcome"),
    ]:
        path = OUTDIR / f"{name}.json"
        path.write_text(
            json.dumps({**meta, "note": note, "by_db": by}, indent=2), encoding="utf-8"
        )
        print(f"[splits] {name:22s} {sum(len(v) for v in by.values()):5d} q  "
              f"({len(by)} dbs) -> {path.relative_to(ROOT)}")

    # sanity: dev and test are disjoint by construction (disjoint database sets)
    assert not (set(dev_split) & set(test_split))
    print(f"[splits] dev/test database overlap: none")
    print(f"[splits] core per database: { {d: len(v) for d, v in sorted(core.items())} }")


if __name__ == "__main__":
    main()
