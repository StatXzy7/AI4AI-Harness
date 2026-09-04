"""Phase-II contamination registry.

Scans the repository for BIRD dev questions that were OBSERVED at any point -- an outcome
recorded, a trace read, an item named in a split. Anything touched is banned from the
confirmatory test.

FAIL-CLOSED. Earlier versions scanned only split files, outcome parquets and
`artifacts/day*/**/*.json`, and silently skipped anything unreadable. That is not a provenance
statement -- an unread file is an unknown, not an absence. This version walks every candidate
file in the repository, and any file it cannot read is reported in `unscanned` rather than
ignored. A non-empty `unscanned` list means the registry is INCOMPLETE and must not be cited.

Scope limits that remain, and are stated in the paper rather than hidden:
  * Git history is not walked; only the working tree at scan time.
  * Filesystem scanning cannot establish that a human never read a question, nor that a
    pretrained builder never encountered public BIRD data. The defensible claim is
    "no project-specific adaptive use", not "never seen".

Output: artifacts/phase2/touched_items.json
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIRD_DEV = ROOT / "external" / "data" / "bird" / "dev_20240627" / "dev.json"
OUT = ROOT / "artifacts" / "phase2" / "touched_items.json"

# directories that hold project artifacts; external/ is the read-only corpus and .git is history
SCAN_DIRS = ["artifacts", "experiment", "paper", "refine-logs", "review-stage"]
TEXT_SUFFIXES = {".json", ".jsonl", ".csv", ".log", ".md", ".txt", ".yaml", ".yml", ".py"}
TASK_RE = re.compile(r'([a-z][a-z_0-9]*)#(\d{1,4})')

# The Phase-II split DEFINITIONS enumerate every index of the test databases. Writing a split
# file selects items; it does not observe any outcome or trace. Counting them as exposure would
# mark the entire dev set touched and is a false positive. Phase-I splits are NOT excluded:
# those items were selected and then actually evaluated.
EXCLUDE_NAMES = {"split_p2_test.json", "split_p2_test_core.json", "split_p2_dev.json",
                 "touched_items.json"}


def local_index_map() -> dict[str, list[int]]:
    """db_id -> global question_ids, in the order eval_questions() yields them."""
    dev = json.loads(BIRD_DEV.read_text(encoding="utf-8"))
    by_db: dict[str, list[int]] = defaultdict(list)
    for e in dev:
        by_db[e["db_id"]].append(e["question_id"])
    return dict(by_db)


def scan(valid_dbs: set[str]):
    touched: dict[str, set[int]] = defaultdict(set)
    sources: dict[str, int] = {}
    unscanned: list[str] = []

    def note(rel: str, hits: int) -> None:
        if hits:
            sources[rel] = sources.get(rel, 0) + hits

    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(ROOT))
            if p.name in EXCLUDE_NAMES:
                continue
            suf = p.suffix.lower()

            if suf == ".parquet":
                try:
                    import pandas as pd

                    df = pd.read_parquet(p, columns=["task_id"])
                except Exception:
                    # not a task-keyed parquet (or unreadable): fall back to a raw byte scan so
                    # the file is still accounted for rather than silently dropped
                    try:
                        blob = p.read_bytes().decode("latin-1", "ignore")
                    except Exception as e:  # noqa: BLE001
                        unscanned.append(f"{rel}: {type(e).__name__}")
                        continue
                    hits = 0
                    for m in TASK_RE.finditer(blob):
                        if m.group(1) in valid_dbs:
                            touched[m.group(1)].add(int(m.group(2)))
                            hits += 1
                    note(rel, hits)
                    continue
                hits = 0
                for tid in df["task_id"].astype(str).unique():
                    m = TASK_RE.fullmatch(tid)
                    if m and m.group(1) in valid_dbs:
                        touched[m.group(1)].add(int(m.group(2)))
                        hits += 1
                note(rel, hits)
                continue

            if suf not in TEXT_SUFFIXES:
                continue
            try:
                raw = p.read_text(encoding="utf-8", errors="strict")
            except UnicodeDecodeError:
                try:                       # pdftotext dumps and similar: decode lossily, still scan
                    raw = p.read_text(encoding="latin-1", errors="replace")
                except Exception as e:  # noqa: BLE001
                    unscanned.append(f"{rel}: {type(e).__name__}")
                    continue
            except Exception as e:  # noqa: BLE001
                unscanned.append(f"{rel}: {type(e).__name__}")
                continue

            hits = 0
            for m in TASK_RE.finditer(raw):
                if m.group(1) in valid_dbs:
                    touched[m.group(1)].add(int(m.group(2)))
                    hits += 1
            # split files name indices under by_db without the 'db#idx' spelling
            if suf == ".json" and ("split" in p.name or "by_db" in raw[:4000]):
                try:
                    d_ = json.loads(raw)
                except Exception:
                    d_ = None
                if isinstance(d_, dict):
                    for db, idxs in (d_.get("by_db") or {}).items():
                        if db in valid_dbs and isinstance(idxs, list):
                            for i in idxs:
                                if isinstance(i, int):
                                    touched[db].add(i)
                                    hits += 1
                    if not d_.get("by_db"):
                        for key in ("build_ids", "eval_ids"):
                            for i in d_.get(key) or []:
                                if isinstance(i, int):
                                    touched["card_games"].add(i)
                                    hits += 1
            note(rel, hits)

    return touched, sources, unscanned


def main() -> None:
    idx_map = local_index_map()
    valid = set(idx_map)
    touched, sources, unscanned = scan(valid)

    clean: dict[str, list[int]] = {}
    qids: list[int] = []
    for db, idxs in sorted(touched.items()):
        keep = sorted(i for i in idxs if 0 <= i < len(idx_map[db]))
        if keep:
            clean[db] = keep
            qids.extend(idx_map[db][i] for i in keep)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "complete": not unscanned,
        "unscanned": unscanned,
        "scan_dirs": SCAN_DIRS,
        "caveats": ["git history not walked", "cannot establish human or pretraining exposure"],
        "touched": clean,
        "touched_qids": sorted(qids),
        "sources": dict(sorted(sources.items(), key=lambda kv: -kv[1])[:60]),
    }, indent=2), encoding="utf-8")

    total = {db: len(v) for db, v in idx_map.items()}
    print(f"[registry] BIRD dev: {sum(total.values())} questions / {len(total)} databases")
    for db in sorted(total):
        t = len(clean.get(db, []))
        flag = "  <-- TOUCHED" if t else ""
        print(f"    {db:28s} {t:4d} / {total[db]:4d}{flag}")
    print(f"[registry] TOTAL touched = {len(qids)} -> untouched pool = {sum(total.values()) - len(qids)}")
    print(f"[registry] files contributing hits: {len(sources)}")
    if unscanned:
        print(f"[registry] INCOMPLETE -- {len(unscanned)} unreadable file(s):")
        for u in unscanned[:10]:
            print(f"    {u}")
    else:
        print("[registry] complete: every candidate file was read")


if __name__ == "__main__":
    main()
