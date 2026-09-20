"""Render the known-truth calibration results into a compact LaTeX table.

Reads artifacts/diagnostics/calibration_v3/calibration_results.json and
writes paper/latex/calibration_table.tex: one row per (scenario, design
cell) showing the false-support (nulls) / power (alternatives) rates of
the legacy plug-in versus the clone-calibrated v3 decision at the actual
acquisition design, plus the R-sweep rows.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "artifacts/diagnostics/calibration_v3/calibration_results.json"
OUT = ROOT / "paper/latex/calibration_table.tex"

# scenarios shown in the paper, grouped; columns: plugin FPR/power, v3
# FPR/power at the (9,400,R) design and the R sweep
ORDER = [
    ("equal_const", "equal ability $q{=}0.9$ (const.)", "null"),
    ("equal_hetero", "equal ability + task difficulty", "null"),
    ("dominance_clean", "dominance, dominant $=$ best fixed", "null"),
    ("dominance_reviewer", "dominance: others $0.9$ vs bare $0.5$", "null"),
    ("dominance_hetero", "dominance + heterogeneous tasks", "null"),
    ("cross_mid", "crossover (cyclic), $H\\approx0.9$\\,pp", "alt"),
    ("cross_strong", "crossover (cyclic), $H\\approx1.8$\\,pp", "alt"),
    ("cross_vstrong", "crossover (cyclic), $H\\approx4.2$\\,pp", "alt"),
    ("two_specialist", "two strong specialists, $H{\\approx}17.5$\\,pp", "alt"),
]


def cell(results, scenario, M=9, T=400, R=3, missing="complete"):
    for r in results:
        if (r["scenario"] == scenario and r["M"] == M and r["T"] == T
                and r["R"] == R and r["missing"] == missing):
            return r
    return None


def pct(x):
    return "---" if x is None else f"{100 * x:.0f}"


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    results = data["results"]
    short = {
        "equal_const": r"equal $q{=}0.9$$^\dagger$",
        "equal_hetero": r"equal + difficulty$^\dagger$",
        "dominance_clean": None,
        "dominance_reviewer": r"$0.5/0.9$ dominance$^\dagger$",
        "dominance_hetero": r"dominance$^\dagger$",
        "cross_mid": r"cross $H{\approx}0.9$\,pp",
        "cross_strong": r"cross $H{\approx}1.8$\,pp",
        "cross_vstrong": r"cross $H{\approx}4.2$\,pp",
        "two_specialist": r"two strong specialists, $H{=}17.5$\,pp",
    }
    lines = [
        r"\renewcommand{\arraystretch}{0.95}",
        r"\setlength{\tabcolsep}{4pt}",
        r"\footnotesize",
        r"\begin{tabular}{@{}lcccccccc@{}}",
        r"\toprule",
        r" & \multicolumn{2}{c}{$R{=}3$} &"
        r" \multicolumn{2}{c}{$R{=}10$} & \multicolumn{2}{c}{$R{=}20$} &"
        r" abst. \\",
        r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}"
        r"\cmidrule(lr){8-8}",
        r"regime & plug & v3 & plug & v3 & plug & v3 & $R{=}3$ \\",
        r"\midrule",
    ]
    for key, label in short.items():
        if label is None:
            continue
        c3 = cell(results, key, R=3)
        c10 = cell(results, key, R=10)
        c20 = cell(results, key, R=20)
        if c3 is None:
            continue
        s3p = c3["statistics"]["plugin_descriptive"]["support_rate"]
        s3v = c3["statistics"]["clone_calibrated_v3"]["support_rate"]
        a3 = c3["statistics"]["clone_calibrated_v3"]["abstain_rate"]
        def pair(c):
            if not c:
                return "---", "---"
            return (pct(c["statistics"]["plugin_descriptive"]["support_rate"]),
                    pct(c["statistics"]["clone_calibrated_v3"]["support_rate"]))
        s10p, s10v = pair(c10)
        s20p, s20v = pair(c20)
        lines.append(
            f"{label} & {pct(s3p)} & {pct(s3v)} & {s10p} & {s10v} & "
            f"{s20p} & {s20v} & {pct(a3)} \\\\")
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        "",
        r"{\scriptsize $^\dagger$Null ($H{=}0$): false-support \%, nominal "
        r"5\%; else power \%. $M{=}9,T{=}400$, $B{=}300$ at $R{=}3$ ($150$ "
        r"sweeps), 300 randomizations. Wilson intervals and the full "
        r"$M,T,R$, missingness grid in Appendix~\ref{app:diagnostics}.}",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
