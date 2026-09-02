"""Map prose arXiv-ID mentions in converted LaTeX sections to \\citep commands."""
import re
from pathlib import Path

L = Path(__file__).resolve().parent.parent / "paper" / "latex"
BS = chr(92)
M = {
    "2607.08124": "tthe2026", "2606.09498": "selfharness2026", "2608.25593": "jitagent2026",
    "2608.20169": "coevolve2026", "2608.27311": "harnesslens2026", "2607.13683": "gatedqd2026",
    "2607.13285": "handbook2026", "2604.06753": "sts2026", "2605.29668": "grasp2026",
    "2608.13951": "helix2026", "2607.05752": "cfrouting2026", "2607.11399": "agenticrouting2026",
    "2607.18235": "nouniversal2026", "2605.26731": "nonmonotone2026",
}
citep = BS + BS + "citep"  # -> \citep literal in replacement string

for f in sorted(L.glob("sec_*.tex")):
    t = f.read_text(encoding="utf-8")
    n = 0
    for aid, key in M.items():
        for pat in (r"\(arXiv:" + aid + r"\)", r"\(" + aid + r"\)", r"arXiv preprint " + aid):
            t2 = re.sub(pat, citep + "{" + key + "}", t)
            if t2 != t:
                n += 1
                t = t2
    f.write_text(t, encoding="utf-8")
    if n:
        print(f.name, n, "citations mapped")
