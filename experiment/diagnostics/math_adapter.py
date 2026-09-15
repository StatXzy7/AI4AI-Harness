"""MATH-500 archive adapter for the diagnostics pipeline.

Loads via an explicit frozen manifest (no directory scanning at analysis time);
duplicate (harness, task) keys are an error, never a silent overwrite. Judge v1 is
the archived judge (experiment.gsm8k.collect.is_correct); judge v2 is the
endpoint-sensitive rescoring judge (plan 6: MATH v2 rescore).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from experiment.gsm8k.collect import _norm_latex, _to_float, extract_answer  # noqa: E402
from experiment.diagnostics.core import Population, digest_file  # noqa: E402

ARCHIVE = ROOT / "artifacts/gsm8k_audit"
RUN_FILES = ["run_math500.jsonl", "run_bare_math500.jsonl"]
SPLIT = ARCHIVE / "math500_split.json"
N_EVAL = 400


def judge_v2(pred_text: str, gold: str) -> int:
    """Endpoint/bracket-sensitive judge: identical to v1 except that bracketed
    list answers keep their bracket context (recovered from the raw prediction
    when extraction strips it) and two-element comparisons require matching
    open/closed endpoints; >2-element bracketed lists (coordinate tuples) ignore
    brackets."""
    p = extract_answer(pred_text)
    if p is None:
        return 0
    pf, gf = _to_float(p), _to_float(gold)
    if pf is not None and gf is not None:
        return int(pf == gf)
    np_, ng = _norm_latex(p), _norm_latex(gold)

    def parse(s: str):
        m = re.fullmatch(r"([\(\[])(.+)([\)\]])", s)
        if not m:
            return None
        return m.group(1), m.group(2).split(","), m.group(3)

    # recover bracket context from the RAW prediction / RAW gold strings as a
    # structured list; _norm_latex strips commas (digit-group heuristic) which
    # would collapse "0,1" into one element and erase the endpoint distinction
    def recover_struct(raw: str, extracted_norm: str):
        stripped = re.sub(r"[\s$]", "", str(raw))
        for tok in ("\\left", "\\right", "\\!"):
            stripped = stripped.replace(tok, "")
        for m in re.finditer(r"([\(\[])([^()\[\]]*)([\)\]])", stripped):
            parts = m.group(2).split(",")
            joined = "".join(_norm_latex(x) for x in parts)
            if joined == extracted_norm:
                return m.group(1), parts, m.group(3)
        return None

    rec_p = recover_struct(pred_text, _norm_latex(p))
    rec_g = recover_struct(gold, _norm_latex(gold))
    if rec_p and rec_g:
        lb1, p1, rb1 = rec_p
        lb2, p2, rb2 = rec_g
        if len(p1) != len(p2):
            return 0
        if not all(_norm_latex(a) == _norm_latex(b) for a, b in zip(p1, p2)):
            return 0
        if len(p1) == 2:
            return int(lb1 == lb2 and rb1 == rb2)
        return 1
    if rec_p or rec_g:
        # only one side is a bracketed list -> fall back to normalized strings
        np_ = f"{rec_p[0]}{','.join(rec_p[1])}{rec_p[2]}" if rec_p else np_
        ng = f"{rec_g[0]}{','.join(rec_g[1])}{rec_g[2]}" if rec_g else ng
        return int(_norm_latex(np_) == _norm_latex(ng) or np_ == ng)
    if np_ == ng:
        return 1
    A, B = parse(np_), parse(ng)
    if A and B:
        lb1, p1, rb1 = A
        lb2, p2, rb2 = B
        if len(p1) != len(p2):
            return 0
        if not all(_norm_latex(a) == _norm_latex(b) for a, b in zip(p1, p2)):
            return 0
        if len(p1) == 2:
            return int(lb1 == lb2 and rb1 == rb2)
        return 1
    return 0


def build_manifest() -> dict:
    """Freeze the explicit input manifest (members, tasks, file hashes)."""
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    eval_tasks = split["tasks"][100:]
    task_ids = [f"math500_split#{i}" for i in range(100, 500)]
    gold_by_tid = {task_ids[i]: eval_tasks[i]["gold"] for i in range(N_EVAL)}
    members = set()
    files = []
    for fn in RUN_FILES:
        p = ARCHIVE / fn
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    members.add(json.loads(line)["harness_id"])
        files.append({"file": fn, "sha256": digest_file(p)})
    members = sorted(members)
    meta = {tid: {"stratum": eval_tasks[i]["subject"]}
            for i, tid in enumerate(task_ids)}
    return {
        "purpose": "MATH-500 archive diagnostics manifest (frozen)",
        "archive": "artifacts/gsm8k_audit",
        "files": files,
        "member_ids": members,          # includes 'bare'
        "task_ids": task_ids,
        "dev_task_ids": [],             # dev = first 100, not run in this archive
        "n_eval_tasks": N_EVAL,
        "gold_by_tid": gold_by_tid,
        "task_meta": meta,
        "condition": {"target": "GLM-5.3-Flash", "repeat": 0, "no_cache": False,
                      "judge": "experiment.gsm8k.collect.is_correct"},
    }


def load_population(manifest: dict, dev_task_ids: list[str] | None = None) -> tuple:
    """Return (Population, s1_counters, v2_rescore_rows)."""
    records: dict[tuple, dict] = {}
    dup = conflicts = 0
    for entry in manifest["files"]:
        path = ARCHIVE / entry["file"]
        if digest_file(path) != entry["sha256"]:
            raise ValueError(f"manifest hash mismatch: {entry['file']}")
        with path.open(encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                r = json.loads(line)
                key = (r["harness_id"], r["task_id"], r["repeat"], r["no_cache"])
                if key in records:
                    dup += 1
                    if records[key]["official_correct"] != r["official_correct"]:
                        conflicts += 1
                    continue
                records[key] = {**r, "source_line": line_no}
    members = manifest["member_ids"]
    tasks = manifest["task_ids"]
    n, t = len(members), len(tasks)
    midx = {m: i for i, m in enumerate(members)}
    tidx = {tk: j for j, tk in enumerate(tasks)}
    Y = np.full((n, t), np.nan)
    calls: dict = {}
    v2_rows = []
    for (h, tid, rep, noc), r in records.items():
        if rep != 0 or noc:
            continue  # single-shot matrix = repeat 0, cache on
        if h not in midx or tid not in tidx:
            continue
        gold = manifest["gold_by_tid"].get(tid)
        if gold is None:
            continue
        i, j = midx[h], tidx[tid]
        Y[i, j] = r["official_correct"]
        if r.get("n_llm_calls") is not None:
            calls[(h, tid)] = r["n_llm_calls"]
        if "final_answer" in r:
            v1 = int(r["official_correct"])
            v2 = judge_v2(r.get("final_answer") or "", gold)
            v2_rows.append({"harness_id": h, "task_id": tid,
                            "v1": v1, "v2": v2,
                            "final_answer": (r.get("final_answer") or "")[-2000:]})
    # judge replay: v1 must reproduce archived verdicts (we already read them, so
    # recompute independently to bind judge version to stored verdicts)
    from experiment.gsm8k.collect import is_correct
    judge_replay_mismatches = 0
    for (h, tid, rep, noc), r in records.items():
        if rep != 0 or noc:
            continue
        gold = manifest["gold_by_tid"].get(tid)
        if gold is None or "final_answer" not in r:
            continue
        if is_correct(r["final_answer"], gold) != r["official_correct"]:
            judge_replay_mismatches += 1
    pop = Population(
        member_ids=members,
        source_hashes=["bare" if m == "bare" else f"sha:{m}" for m in members],
        tasks=tasks, Y=Y,
        condition=manifest["condition"], has_bare=True,
        dev_task_ids=dev_task_ids or [],
        task_meta=manifest["task_meta"], calls=calls,
        calls_status="per_record" if calls else "absent_in_archive_rows")
    return pop, {"duplicate_keys": dup, "verdict_conflicts": conflicts,
                 "judge_replay_mismatches": judge_replay_mismatches}, v2_rows
