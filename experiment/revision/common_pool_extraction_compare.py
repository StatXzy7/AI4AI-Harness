"""Paired extraction analysis of an externally hash-pinned, completed raw pool.

No candidate is imported or executed. This isolates extraction on the same
messages; it is not neutral validity, admission, or a full historical bridge.
"""

import argparse
import ast
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from experiment.revision.code_responses import extract_python
from experiment.revision.generation_extraction_audit import GENERATOR, legacy_extractor


def sha(data):
    return hashlib.sha256(data).hexdigest()


def syntax_valid(code):
    if not isinstance(code, str) or not code.strip():
        return False
    try:
        ast.parse(code)
    except (SyntaxError, ValueError):
        return False
    return True


def compare_message(message, legacy):
    old, truncated = (
        legacy(message, "python") if isinstance(message, str) else ("", False)
    )
    new = extract_python(message)
    return dict(
        legacy_syntax_valid=syntax_valid(old),
        new_syntax_valid=syntax_valid(new.code),
        legacy_truncated=truncated,
        new_status=new.status,
        legacy_code_sha256=sha(old.encode("utf-8")) if old else None,
        new_code_sha256=sha(new.code.encode("utf-8")) if new.code is not None else None,
        same_code_bytes=old == new.code,
    )


def analyze(pool_path, expected_sha256):
    """The expected hash must come from the separate raw-pool completion audit."""
    pool_path = Path(pool_path)
    raw = pool_path.read_bytes()
    if sha(raw) != expected_sha256:
        raise ValueError("pool differs from externally pinned hash")
    marker = json.loads(
        pool_path.with_name("POOL_COMPLETE.json").read_text(encoding="utf-8")
    )
    pool = json.loads(raw)
    if (
        marker["pool_sha256"] != expected_sha256
        or marker["run_id"] != pool["run_id"]
        or marker["planned_attempts"] != pool["manifest"]["planned_attempts"]
        or len(pool["tasks"]) != marker["planned_attempts"]
        or len({t["key"] for t in pool["tasks"]}) != len(pool["tasks"])
        or any(t["result"] is None for t in pool["tasks"])
    ):
        raise ValueError("incomplete or inconsistent completed export")
    legacy = legacy_extractor()
    rows = []
    for task in pool["tasks"]:
        r = task["result"]
        if asdict(extract_python(r["message"])) != r["extraction"]:
            raise ValueError("current extraction differs from saved producer result")
        rows.append(
            dict(
                task_key=task["key"],
                identity=r["identity"],
                generation_condition=r["generation_condition"],
                strategy=r["strategy"],
                **compare_message(r["message"], legacy)
            )
        )
    counts = Counter(
        (
            r["generation_condition"],
            r["strategy"],
            r["legacy_syntax_valid"],
            r["new_syntax_valid"],
        )
        for r in rows
    )
    sources = [
        Path(__file__),
        GENERATOR,
        Path(__file__).with_name("code_responses.py"),
        Path(__file__).with_name("generation_extraction_audit.py"),
    ]
    return dict(
        scope=__doc__,
        pool_sha256=expected_sha256,
        run_id=pool["run_id"],
        n_attempts=len(rows),
        source_bindings={str(p.resolve()): sha(p.read_bytes()) for p in sources},
        paired_counts=[
            dict(condition=c, strategy=s, legacy_valid=a, new_valid=b, count=n)
            for (c, s, a, b), n in counts.items()
        ],
        rows=rows,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise ValueError("analysis output already exists")
    result = analyze(args.pool, args.expected_sha256)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
