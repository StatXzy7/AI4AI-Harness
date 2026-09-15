"""Unified diagnostics CLI.

Commands:
  diagnose-math [--dev-tasks N]   Run S1-S5 on the MATH-500 archive (+ judge-v2 rescore summary)
  diagnose-bird                   Run S1-S5 on the BIRD phase2 archive (18 cells x arms)
  controls [--phase calibration|blinded]   Freeze/run the control package, M0-M3 matrix
  inventory                       Full archive inventory rows (MATH + BIRD)

Every run writes to a fresh artifacts/diagnostics/<date>/<run_id>/ directory; frozen
history is never overwritten. Offline: no model API calls.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from experiment.diagnostics import core, controls as ctl
from experiment.diagnostics.core import (INSUFFICIENT, REFUTED, SUPPORTED,
                                         assemble_report)
from experiment.diagnostics.math_adapter import (build_manifest, judge_v2,
                                                 load_population)
from experiment.diagnostics.bird_adapter import load_bird

ROOT = Path(__file__).resolve().parents[2]


def _outdir(tag: str) -> Path:
    stamp = _dt.datetime.now().strftime("%Y%m%d")
    run_id = f"{stamp}_{tag}_{hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:8]}"
    out = ROOT / "artifacts/diagnostics" / stamp / run_id
    out.mkdir(parents=True, exist_ok=True)
    return out


def _s3_for_pop(pop) -> dict:
    return core.s3_stability({"single": pop})


def diagnose_math(dev_tasks: int, out: Path) -> dict:
    manifest = build_manifest()
    # frozen dev split for policy training = first `dev_tasks` eval tasks (the
    # archive contains no separate dev execution; dev-task ids are held out of B/D/E)
    dev_ids = manifest["task_ids"][:dev_tasks]
    manifest["dev_task_ids"] = dev_ids
    pop, counters, v2_rows = load_population(manifest, dev_ids)
    # remove dev tasks from the eval matrix for D/E/B claims
    ev_idx = [j for j, t in enumerate(pop.tasks) if t not in set(dev_ids)]
    pop_eval = core.Population(
        member_ids=pop.member_ids, source_hashes=pop.source_hashes,
        tasks=[pop.tasks[j] for j in ev_idx], Y=pop.Y[:, ev_idx],
        condition=pop.condition, has_bare=True, dev_task_ids=dev_ids,
        task_meta={t: pop.task_meta[t] for t in pop.tasks if t in pop.task_meta},
        calls={k: v for k, v in pop.calls.items() if k[1] not in set(dev_ids)})
    s1 = core.s1_integrity(manifest, pop, counters["judge_replay_mismatches"],
                           counters["duplicate_keys"], [])
    s2 = core.s2_decomposition(pop_eval)
    s3 = _s3_for_pop(pop)
    # D/E train on the full matrix (dev tasks included) and evaluate only on
    # held-out eval tasks - the earlier eval-only pass-through made dev_idx
    # empty and mechanically abstained (fixed per cold-start audit).
    s4 = core.s4_selectability(pop)
    s5 = core.s5_cost(pop, s4)
    report = assemble_report(s1, s2, s3, s4, s5)

    # MATH judge-v2 rescore: per-record differences + aggregate impact
    flips = [r for r in v2_rows if r["v1"] != r["v2"]]
    per_h = {}
    for r in flips:
        per_h.setdefault(r["harness_id"], []).append(r)
    v2_summary = {
        "judge_v2": "endpoint/bracket-sensitive (math_adapter.judge_v2)",
        "n_rows": len(v2_rows), "n_flips": len(flips),
        "flips_false_accept": sum(1 for r in flips if r["v1"] == 1 and r["v2"] == 0),
        "flips_false_reject": sum(1 for r in flips if r["v1"] == 0 and r["v2"] == 1),
        "per_harness_flip_counts": {h: len(v) for h, v in sorted(per_h.items())},
    }
    result = {"manifest_sha256": hashlib.sha256(
        json.dumps({k: v for k, v in manifest.items() if k != "gold_by_tid"},
                   sort_keys=True).encode()).hexdigest(),
        "K_stats": pop.k_stats(), "report": report, "judge_v2_rescore": v2_summary}
    (out / "math_diagnosis.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if flips:
        with (out / "math_judge_v2_flips.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["harness_id", "task_id", "v1", "v2", "final_answer"])
            w.writeheader()
            w.writerows(flips)
    return result


def diagnose_bird(out: Path) -> dict:
    data = load_bird()
    cells = data["cells"]
    cell_reports = {}
    s3_state = _s3_for_pop(next(iter(cells.values())))  # all cells repeat-0 only
    agg = {arm: [] for arm in "ABCD"}
    total_dups = sum(a.get("duplicates", 0) for a in data["audit"].values())
    total_conf = sum(a.get("verdict_conflicts", 0) for a in data["audit"].values())
    hash_conflicts = [f"{key}|{h}" for key, pop0 in cells.items()
                      for h in pop0.source_hashes if str(h).startswith("CONFLICT")]
    for key, pop in sorted(cells.items()):
        manifest_mock = {"member_ids": pop.member_ids, "task_ids": pop.tasks}
        missing = int(np.isnan(pop.Y).sum())
        s1 = core.s1_integrity(manifest_mock, pop, 0, total_dups + total_conf,
                               hash_conflicts)
        s1["checks"]["missing_cells_le_1pct"] = missing / pop.Y.size <= 0.01
        s1["missing_cells"] = missing
        if missing and not s1["checks"]["missing_cells_le_1pct"] and s1["state"] == SUPPORTED:
            s1["state"] = REFUTED
            s1["blocked"].append("missing_cells_le_1pct")
        s2 = core.s2_decomposition(pop)
        s4 = {"state": INSUFFICIENT,
              "reason": "BIRD archive has no dev/eval split of executions usable for "
                        "policy training; no pre-execution task features archived"}
        s5 = {"state": INSUFFICIENT, "reason": "no per-record call counts in phase2 rows"}
        cell_reports["|".join(map(str, key))] = {
            "A": s1["state"], "B": s2, "C": s3_state["state"], "D": s4, "E": s5,
            "K_stats": pop.k_stats()}
        agg[key[2]].append(s2)
    summary = {arm: {
        "mean_headroom": round(float(np.mean([b["headroom"] for b in v])), 4),
        "mean_oracle": round(float(np.mean([b["oracle_accuracy"] for b in v])), 4),
        "mean_best_fixed": round(float(np.mean([b["best_fixed_accuracy"] for b in v])), 4),
        "mean_bare": round(float(np.mean([b["bare_accuracy"] for b in v])), 4),
        "B_states": {s: sum(1 for b in v if b["state"] == s)
                     for s in (SUPPORTED, REFUTED, INSUFFICIENT)},
    } for arm, v in agg.items()}
    result = {"n_cells": len(cells), "n_tasks": len(data["tasks"]),
              "input_audit": data["audit"], "cell_reports": cell_reports,
              "arm_summary": summary, "C_global": s3_state,
              "note": "historical primary rows are repeat 0 / cache on -> C abstains "
                      "by the frozen rule (plan 3.C), not an absence of difference"}
    (out / "bird_diagnosis.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def _run_diagnostic(pop: core.Population) -> dict:
    manifest_mock = {"member_ids": pop.member_ids, "task_ids": pop.tasks}
    s1 = core.s1_integrity(manifest_mock, pop, pop.judge_replay_mismatches,
                           pop.duplicate_keys, [])
    s2 = core.s2_decomposition(pop)
    s3 = _s3_for_pop(pop)
    s4 = core.s4_selectability(pop)
    s5 = core.s5_cost(pop, s4)
    return {"A": s1["state"], "B": s2["state"], "C": s3["state"], "D": s4["state"],
            "E": s5["state"],
            "detail": {"A": s1, "B": s2, "D": s4, "E": s5}}


def _m0_metrics(pop: core.Population) -> dict:
    """Traditional single-shot population metrics only (mean member acc, oracle).

    Comparison reference only; still denominator-preserving on missing cells."""
    Y = pop.Y
    return {"mean_member_accuracy": round(float(np.nansum(Y) / Y.size), 4),
            "oracle_accuracy": round(float(np.nansum(np.nanmax(Y, axis=0)) / Y.shape[1]), 4)}


def _m1_metrics(pop: core.Population) -> dict:
    """Competent decomposition baseline + basic integrity checks."""
    Y = pop.Y
    dup_cols = len(pop.tasks) - len(set(pop.tasks))
    return {**_m0_metrics(pop),
            "best_fixed": round(float((np.nansum(Y, axis=1) / Y.shape[1]).max()), 4),
            "headroom": round(float(np.nansum(np.nanmax(Y, axis=0)) / Y.shape[1]
                                    - (np.nansum(Y, axis=1) / Y.shape[1]).max()), 4),
            "integrity": {"duplicate_task_ids": dup_cols,
                          "missing_cells": int(np.isnan(Y).sum())}}


def run_controls(phase: str, out: Path) -> dict:
    package = ctl.build_package()
    if phase == "blinded":
        ch_paths = sorted(Path(ROOT, "artifacts/diagnostics").glob(
            "**/astra_challenges_result.json"))
        if ch_paths:
            ch = json.loads(ch_paths[-1].read_text())
            spec = json.loads(Path(ROOT, "review-stage/astra_20260915/challenge_spec.json").read_text())
            for c in spec["challenges"]:
                package["controls"].append({
                    "cid": c["id"], "cls": c["description"], "instance": 0,
                    "instance_phase": "blinded_challenge",
                    "description": c["generating_rule"][:300],
                    "expected": {**c["expected"], "A": "SUPPORTED"},
                    "n_members": None, "n_tasks": None,
                    "note": "auditor challenge, pre-committed by hash; A expectation derived "
                            "from the challenge's own no-corruption constraints"})
            package["blinded"] = package["blinded"] + ["CH1", "CH2"]
    (out / f"control_manifest_{phase}.json").write_text(
        json.dumps(package, indent=2), encoding="utf-8")
    classes = ("A", "B", "C", "D", "E")
    rows = []
    for c in package["controls"]:
        if c["instance_phase"] != phase:
            continue
        pop = ctl.get_control(c["cid"], c["instance"])
        got = _run_diagnostic(pop)
        exp = c["expected"]
        verdict = {k: "OK" if got[k] == exp[k] else "WRONG" for k in classes}
        rows.append({"control": f"{c['cid']}#{c['instance']}",
                     "description": c["description"], "expected": exp,
                     "got": {k: got[k] for k in classes},
                     "verdict": verdict})
    if phase == "blinded":
        ch_paths = sorted(Path(ROOT, "artifacts/diagnostics").glob(
            "**/astra_challenges_result.json"))
        if ch_paths:
            ch = json.loads(ch_paths[-1].read_text())
            for cid in ("CH1", "CH2"):
                rows.append({"control": cid,
                             "description": "auditor challenge (pre-committed by hash)",
                             "expected": ch[cid]["expected"],
                             "got": ch[cid]["got"],
                             "verdict": {k: ("OK" if ch[cid]["got"][k] == ch[cid]["expected"][k]
                                             else "WRONG") for k in ch[cid]["expected"]}})
    n = len(rows)
    wrong = sum(1 for r in rows if "WRONG" in r["verdict"].values())
    cells = [(r, k) for r in rows for k in r["expected"]]
    n_nonsup = sum(1 for r, k in cells if r["expected"][k] != SUPPORTED)
    false_support = sum(1 for r, k in cells
                        if r["got"][k] == SUPPORTED and r["expected"][k] != SUPPORTED)
    n_clear = sum(1 for r, k in cells
                  if r["expected"][k] in (SUPPORTED, REFUTED))
    wrongful_abstain = sum(1 for r, k in cells
                           if r["got"][k] == INSUFFICIENT
                           and r["expected"][k] in (SUPPORTED, REFUTED))
    metrics = {
        "n_controls": n, "n_any_wrong": wrong,
        "N_nonSUPPORTED": n_nonsup, "N_clear": n_clear,
        "false_support_rate": round(false_support / max(1, n_nonsup), 4),
        "false_support_pass": false_support / max(1, n_nonsup) <= 0.1,
        "wrongful_abstain": wrongful_abstain,
        "abstain_cap_pass": wrongful_abstain <= max(3, int(0.3 * n_clear)),
        "abstain_rate_all_cells": round(sum(1 for r, k in cells
                                            if r["got"][k] == INSUFFICIENT)
                                        / max(1, len(cells)), 4),
        "positive_control_recognized": all(
            r["verdict"][k] == "OK" for r in rows
            if r["control"].startswith("C4") for k in ("D", "E")),
    }
    result = {"phase": phase, "metrics": metrics, "rows": rows,
              "thresholds": {"false_support_rate_max": 0.1,
                             "abstain_cap": "3 or 30% of N_clear"},
              "m0_example": _m0_metrics(ctl.get_control("C4", 1)),
              "m1_example": _m1_metrics(ctl.get_control("C4", 1)),
              "note": "M0/M1 are reported as comparison references; the full method "
                      "comparison table is assembled in CONTROL_VALIDATION.json"}
    (out / f"control_validation_{phase}.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    return result


def inventory(out: Path) -> dict:
    """Full archive inventory rows (plan 6): every member x task pair, staged."""
    manifest = build_manifest()
    pop, counters, _ = load_population(manifest)
    rows = []
    for i, h in enumerate(pop.member_ids):
        for j, t in enumerate(pop.tasks):
            v = pop.Y[i, j]
            rows.append({"archive": "math500", "member": h, "task": t,
                         "state": "included" if not np.isnan(v) else "missing",
                         "verdict": None if np.isnan(v) else int(v)})
    data = load_bird()
    for key, p in sorted(data["cells"].items()):
        for i, h in enumerate(p.member_ids):
            for j, t in enumerate(p.tasks):
                v = p.Y[i, j]
                rows.append({"archive": "bird_phase2", "member": f"{key}|{h}",
                             "task": t,
                             "state": "included" if not np.isnan(v) else "missing",
                             "verdict": None if np.isnan(v) else int(v)})
    with (out / "ARCHIVE_INVENTORY.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["archive", "member", "task", "state", "verdict"])
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        counts[r["archive"]] = counts.get(r["archive"], 0) + 1
    return {"n_rows": len(rows), "by_archive": counts}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["diagnose-math", "diagnose-bird",
                                        "controls", "inventory", "all"])
    ap.add_argument("--phase", default="calibration", choices=["calibration", "blinded"])
    ap.add_argument("--dev-tasks", type=int, default=80,
                    help="MATH eval tasks held out as dev split for D/E (frozen run uses 80)")
    args = ap.parse_args()
    tag = args.command.replace("-", "_")
    out = _outdir("all" if args.command == "all" else tag)
    print(f"[diagnostics] run dir: {out}")
    if args.command in ("diagnose-math", "all"):
        r = diagnose_math(args.dev_tasks, out)
        print(json.dumps({"B": r["report"]["B_single_shot_coverage"]["state"],
                          "D": r["report"]["D_pre_execution_selectability"]["state"],
                          "E": r["report"]["E_policy_utility"]["state"],
                          "v2_flips": r["judge_v2_rescore"]["n_flips"]}, indent=1))
    if args.command in ("diagnose-bird", "all"):
        r = diagnose_bird(out)
        print(json.dumps(r["arm_summary"], indent=1))
    if args.command in ("controls", "all"):
        r = run_controls(args.phase, out)
        print(json.dumps(r["metrics"], indent=1))
    if args.command in ("inventory", "all"):
        r = inventory(out)
        print(json.dumps(r, indent=1))


if __name__ == "__main__":
    main()
