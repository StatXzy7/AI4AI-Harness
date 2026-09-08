"""GSM8K audit collector + judge: run harnesses over the frozen eval half,
numeric-exact-match judge, resumable JSONL (mirror of phase2/collect.py).

Judge: strip commas/$/whitespace; correct iff the extracted number equals the
gold float (within 1e-6 relative tolerance, so "18.0" == "18").
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiment"))
sys.path.insert(0, str(ROOT / "experiment" / "gsm8k"))
sys.path.insert(0, str(ROOT / "external" / "TTHE"))

DEFAULT_SPLIT = ROOT / "artifacts" / "gsm8k_audit" / "task_split.json"


def _boxed_content(text: str):
    """Last \\boxed{...} with balanced nested braces, or None."""
    idx = text.rfind("\\boxed")
    while idx != -1:
        i = text.find("{", idx)
        if i == -1:
            return None
        depth = 0
        for j in range(i, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    return text[i + 1: j].strip()
        return None                    # unbalanced (truncated reply)
    return None


def extract_answer(text: str):
    """Final answer string: '#### x' line wins; else last \\boxed{...}; else the
    last $...$ math block; else the last numeric token."""
    if not text:
        return None
    m = re.findall(r"####\s*(.+?)(?:\n|$)", text)
    if m:
        return m[-1].strip()
    b = _boxed_content(text)
    if b is not None:
        return b
    m = re.findall(r"\$([^$]+)\$", text)
    if m:
        return m[-1].strip()
    m = re.findall(r"([\-]?\d[\d,]*\.?\d*)", text.replace("$", ""))
    return m[-1] if m else None


def _to_float(s: str):
    """Parse ints, decimals, plain 'a/b', and latex '\\frac{a}{b}'."""
    t = str(s).strip().replace(",", "").replace("$", "")
    try:
        return float(t)
    except ValueError:
        pass
    m = re.fullmatch(r"\\frac\{(-?[\d.]+)\}\{(-?[\d.]+)\}", t) or re.fullmatch(
        r"(-?[\d.]+)/(-?[\d.]+)", t)
    if m:
        try:
            return float(m.group(1)) / float(m.group(2))
        except (ValueError, ZeroDivisionError):
            return None
    return None


def _norm_latex(s: str) -> str:
    """Canonicalize a latex/ascii answer string for exact comparison."""
    t = str(s).strip()
    t = t.replace("$", "").replace(" ", "").replace("\\!", "")
    t = t.replace("\\left", "").replace("\\right", "")
    t = t.replace("dfrac", "frac").replace("tfrac", "frac")
    t = t.replace("\\displaystyle", "")
    t = re.sub(r"\\text\{[^{}]*\}", "", t)
    t = re.sub(r"\\mbox\{[^{}]*\}", "", t)
    t = re.sub(r"^\((.*)\)$", r"\1", t)          # strip one outer paren pair
    t = re.sub(r"\\frac\{(-?[^{}]+)\}\{(-?[^{}]+)\}", r"\1/\2", t)   # \frac{a}{b} -> a/b
    t = t.replace("{", "").replace("}", "")      # \sqrt{3} -> \sqrt3, tuples, sets
    t = t.rstrip(".")
    t = re.sub(r"^(-?\d+)\.0+$", r"\1", t)       # 3.0 -> 3
    t = re.sub(r"^\+", "", t)
    return t


def is_correct(pred_text: str, gold: str) -> int:
    """Numeric equality if both parse as numbers; else normalized string equality."""
    p = extract_answer(pred_text)
    if p is None:
        return 0
    pf, gf = _to_float(p), _to_float(gold)
    if pf is not None and gf is not None:
        return int(pf == gf)
    return int(_norm_latex(p) == _norm_latex(gold))


def load_done(path: Path) -> set[tuple]:
    done = set()
    if not path.exists():
        return done
    for line in open(path, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        done.add((r["target"], r["harness_id"], r["task_id"]))
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--harnesses", required=True, help="'all' or comma-separated names")
    ap.add_argument("--target", required=True)
    ap.add_argument("--split", default=str(DEFAULT_SPLIT),
                    help="task split json (default: gsm8k 300-task split)")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    split = json.loads(Path(a.split).read_text())
    eval_tasks = split["tasks"][100:]          # dev = first 100, eval = rest
    domain = Path(a.split).stem

    # target fixed before bridge import (bridge builds its client at import);
    # math prompts get their own cache file so the SQL experiments' shared cache is untouched
    os.environ["SOLVER_MODEL"] = a.target
    if not os.environ.get("SQL_SOLVER_CACHE"):
        os.environ["SQL_SOLVER_CACHE"] = str(ROOT / "artifacts" / "gsm8k_audit" / "solver_cache.json")
    if a.no_cache:
        os.environ["SQL_SOLVER_CACHE"] = str(
            ROOT / "artifacts" / "gsm8k_audit" / f".nocache_{int(time.time())}.json")

    from text_to_sql import bridge
    if a.no_cache:
        bridge._CACHE.get_or_call = lambda parts, produce: produce()
        print("[collect] solver cache BYPASSED")

    import generate as gen                       # noqa: PLC0415  (gsm8k.generate)

    out = Path(a.out)
    out = out if out.is_absolute() else ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(out)
    print(f"[collect] {len(done)} cells already recorded in {out.name}")
    print(f"[collect] {len(eval_tasks)} eval tasks ({domain}) | target={a.target}")

    if a.harnesses == "all":
        names = sorted(p.stem for p in gen.AGENTS_DIR.glob("gsm_*.py"))
    else:
        names = [s.strip() for s in a.harnesses.split(",") if s.strip()]

    lock = threading.Lock()
    fh = open(out, "a", encoding="utf-8")

    for name in names:
        try:
            code = (gen.AGENTS_DIR / f"{name}.py").read_text(encoding="utf-8")
            gen.load_harness(name)               # import check
        except Exception as e:
            print(f"  [skip] {name}: {e!r}")
            continue
        chash = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]
        todo = [ex for i, ex in enumerate(eval_tasks)
                if (a.target, name, f"{domain}#{100 + i}") not in done]
        if not todo:
            print(f"  [have] {name}: complete")
            continue

        def solve_one(pair):
            i, ex = pair
            tid = f"{domain}#{100 + i}"
            h = gen.load_harness(name)           # fresh instance per task (mutable _trace)
            t0 = time.time()
            try:
                ans = h.solve(ex["question"]) or ""
                err = None
            except Exception as e:  # noqa: BLE001
                ans, err = "", repr(e)[:300]
            ms = int((time.time() - t0) * 1000)
            return {
                "target": a.target, "harness_id": name, "task_id": tid,
                "db_id": ex.get("subject", domain), "repeat": 0, "no_cache": bool(a.no_cache),
                "official_correct": is_correct(ans, ex["gold"]),
                "legacy_correct": None,
                "final_answer": ans[-2000:], "n_llm_calls": len(h._trace),
                "n_execs": 0, "latency_ms": ms, "code_hash": chash, "error": err,
            }

        n_ok = 0
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            for k, rec in enumerate(ex.map(solve_one, list(enumerate(eval_tasks)))):
                if (a.target, name, rec["task_id"]) in done:
                    continue
                with lock:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    if k % 50 == 0:
                        fh.flush()
                n_ok += rec["official_correct"]
                if (k + 1) % 100 == 0:
                    print(f"    {name}: {k+1}/{len(eval_tasks)} acc={n_ok/(k+1):.3f}", flush=True)
        fh.flush()
        print(f"  [done] {name}: acc={n_ok/len(eval_tasks):.3f}", flush=True)

    fh.close()
    try:
        bridge._CACHE.flush()
    except Exception:
        pass
    print(f"[collect] wrote {out}")


if __name__ == "__main__":
    main()
