"""Append the two_specialist scenario cells to an existing calibration
artifact (the other scenarios are expensive and unchanged)."""
import json
from pathlib import Path

from experiment.diagnostics.calibration_run import paper_cells, run_cell

ROOT = Path(__file__).resolve().parents[2]
p = ROOT / "artifacts/diagnostics/calibration_v3/calibration_results.json"
def main() -> None:
    r = json.loads(p.read_text(encoding="utf-8"))
    cells = paper_cells(300, 150)
    new = []
    for k, (M, T, Rv, mn, f, me, n) in enumerate(cells):
        x = run_cell("two_specialist", "crossover", M, T, Rv, mn, f, me, n,
                     n_workers=8)
        x.update(M=M, T=T, R=Rv, missing=mn)
        new.append(x)
        v = x["statistics"]["clone_calibrated_v3"]["support_rate"]
        print(f"{k + 1}/{len(cells)} R={Rv} {mn} power={v}", flush=True)
    r["results"].extend(new)
    p.write_text(json.dumps(r, indent=1), encoding="utf-8")
    print("total cells", len(r["results"]))


if __name__ == "__main__":
    main()
