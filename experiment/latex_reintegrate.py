"""Reintegrate markdown drafts into LaTeX sections (deterministic, round 3)."""
import re
from pathlib import Path

import pypandoc

D = Path(__file__).resolve().parent.parent / "paper" / "draft"
L = Path(__file__).resolve().parent.parent / "paper" / "latex"
BS = chr(92)


def md_clean(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"\*\(draft.*?\)\*", "", text, flags=re.S)
    return text


def to_latex(text: str) -> str:
    text = re.sub(r"^# .*?\n", "", text, flags=re.M)
    body = pypandoc.convert_text(text, "latex", format="markdown+smart")
    sec_line = re.compile(BS * 2 + r"section\{[^}]*\}" + BS * 2 + r"label\{[^}]*\}\s*")
    body = sec_line.sub("", body)
    body = re.sub(r"(\\subsection\{)\d+\.\d+\s+", r"\1", body)
    body = body.replace("§§", "Sections ")
    body = re.sub(r"§\s*(\d)", r"Section~\1", body)
    body = body.replace("§", "Section ")
    return body


md = md_clean((D / "05_06_positive_control_protocols.md").read_text(encoding="utf-8"))
i5 = md.find("# §5")
i6 = md.find("# §6")
assert 0 <= i5 < i6, (i5, i6)
(L / "sec_positive.tex").write_text(to_latex(md[i5:i6]), encoding="utf-8")
(L / "sec_protocols.tex").write_text(to_latex(md[i6:]), encoding="utf-8")

(L / "sec_intro.tex").write_text(to_latex(md_clean((D / "01_intro.md").read_text(encoding="utf-8"))), encoding="utf-8")
(L / "sec_setup.tex").write_text(to_latex(md_clean((D / "03_setup.md").read_text(encoding="utf-8"))), encoding="utf-8")
(L / "sec_measurement.tex").write_text(to_latex(md_clean((D / "04_measurement.md").read_text(encoding="utf-8"))), encoding="utf-8")
(L / "sec_related.tex").write_text(to_latex(md_clean((D / "02_related_work.md").read_text(encoding="utf-8"))), encoding="utf-8")

t = md_clean((D / "00_abstract_07_08.md").read_text(encoding="utf-8"))
i7, i8, ib = t.find("## §7"), t.find("## §8"), t.find("## 备档")
(L / "sec_discussion.tex").write_text(to_latex(t[i7:i8]), encoding="utf-8")
(L / "sec_conclusion.tex").write_text(to_latex(t[i8:ib]), encoding="utf-8")

for f in sorted(L.glob("sec_*.tex")):
    t = f.read_text(encoding="utf-8")
    t = t.replace("*)", "")
    f.write_text(t, encoding="utf-8")
    print(f.name, len(t))
