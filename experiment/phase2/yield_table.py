"""Phase-II generation yield table.

Reports the decomposition the SAP asks for -- raw attempt -> valid artifact -> conformant
mechanism -> admitted population -- so that "the builder cannot write it" is never confused
with "what it wrote has no value". Reads only generation logs; touches no outcome data.

    python experiment/phase2/yield_table.py
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "artifacts" / "phase2" / "gen"

ARM_LABEL = {"A": "A free/ungated", "B": "B free/gated",
             "C": "C forced/ungated", "D": "D forced/gated", "E": "E open-mechanism"}


def load():
    out = []
    for f in sorted(GEN.glob("[ABCDE]_*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "K_admitted" not in d:
            continue
        R = d["results"]
        raw = sum(r["n_raw"] for r in R)
        out.append({
            "arm": d["arm"], "builder": d["builder"], "seed": d["seed"],
            "model": d.get("model", "?"), "slots": d["n_slots"], "K": d["K_admitted"],
            "raw": raw,
            "nv": sum(r["n_neutral_valid"] for r in R),
            "mech": sum(r["n_mechanism_pass"] for r in R),
            "gate": d["gate"],
            "verdicts": collections.Counter(
                (a.get("mechanism_detail") or {}).get("verdict")
                for r in R for a in r["attempts"]
                if (a.get("mechanism_detail") or {}).get("verdict")),
            "mech_sigs": [tuple(sorted(k for k, v in (r["contract"] or {}).items()
                                       if k != "name" and v is True))
                          for r in R if r["admitted"] and r.get("contract")],
        })
    return out


def main() -> None:
    rows = load()
    if not rows:
        print("no generation logs yet")
        return

    print("PHASE-II GENERATION YIELD  (dev-side only; no confirmatory outcome involved)\n")
    print(f"{'arm':18s} {'builder':9s} {'seed':>4s} {'K/slots':>8s} {'R_artifact':>11s} "
          f"{'R_fidelity':>11s}  notes")
    print("-" * 92)
    for r in sorted(rows, key=lambda x: (x["arm"], x["builder"], x["seed"])):
        r_art = r["nv"] / r["raw"] if r["raw"] else 0.0
        r_fid = (r["mech"] / r["nv"]) if (r["gate"] and r["nv"]) else float("nan")
        fid = f"{r_fid:.2f}" if r_fid == r_fid else "   -"
        note = ""
        if r["mech_sigs"]:
            uniq = len(set(r["mech_sigs"]))
            note = f"K_mech={uniq}/{len(r['mech_sigs'])}"
        elif r["verdicts"]:
            bad = {k: v for k, v in r["verdicts"].items() if k != "PASS"}
            note = ", ".join(f"{k}x{v}" for k, v in sorted(bad.items())[:2])
        print(f"{ARM_LABEL[r['arm']]:18s} {r['builder']:9s} {r['seed']:>4d} "
              f"{r['K']:>4d}/{r['slots']:<3d} {r['nv']:>4d}/{r['raw']:<3d}={r_art:.2f} "
              f"{fid:>11s}  {note}")

    print("\nPER-ARM TOTALS (pooled over builders and seeds present)")
    by_arm = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
    for r in rows:
        a = by_arm[r["arm"]]
        a[0] += r["raw"]; a[1] += r["nv"]; a[2] += r["mech"]; a[3] += r["K"]; a[4] += r["slots"]
    print(f"{'arm':18s} {'raw':>5s} {'valid':>6s} {'R_artifact':>11s} {'K/slots':>9s} {'R_fidelity':>11s}")
    for arm in sorted(by_arm):
        raw, nv, mech, K, slots = by_arm[arm]
        gated = arm in ("B", "D", "E")
        fid = f"{mech/nv:.2f}" if (gated and nv) else "   -"
        print(f"{ARM_LABEL[arm]:18s} {raw:>5d} {nv:>6d} {nv/raw:>11.2f} "
              f"{K:>4d}/{slots:<4d} {fid:>11s}")

    n_cells = len({(r["builder"], r["seed"]) for r in rows if r["arm"] in ("A", "D")})
    print(f"\npaired (builder x seed) cells with both A and D present: {n_cells}")


if __name__ == "__main__":
    main()
