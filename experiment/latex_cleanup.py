"""One-off cleanup for pandoc-converted LaTeX section files (paper/latex/sec_*.tex)."""
import re
from pathlib import Path

L = Path(__file__).resolve().parent.parent / "paper" / "latex"
BS = chr(92)  # backslash

for f in sorted(L.glob("sec_*.tex")):
    t = f.read_text(encoding="utf-8")
    t = re.sub(r"\*\(draft.*?\)\*", "", t, flags=re.S)
    sec_line = re.compile(BS * 2 + r"section\{[^}]*\}" + BS * 2 + r"label\{[^}]*\}\s*")
    t = sec_line.sub("", t)
    t = re.sub(r"(\\subsection\{)\d+\.\d+\s+", r"\1", t)
    t = t.replace("§§", "Sections ")
    t = re.sub(r"§\s*(\d)", r"Section~\1", t)
    t = t.replace("§", "Section ")
    t = t.replace("*)", "")
    f.write_text(t, encoding="utf-8")
    print(f.name, len(t))
