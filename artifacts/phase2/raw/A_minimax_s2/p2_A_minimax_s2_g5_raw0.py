# Harness that draws several SQL candidates and selects the one whose execution produces the most frequent non-empty result set.
# MECHANISM: vote
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G5(SQLHarness):
    def solve(self, question: str) -> str:
        # ---------- 1. Build prompts ----------
        system_prompt = (
            "You are an expert SQL engineer. Given a schema and a natural language "
            "question, write a single SQLite query that answers it. "
            "Output ONLY the SQL statement, with no markdown fences and no commentary."
        )
        user_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return a single SQL statement and nothing else."
        )

        # ---------- 2. Draw several candidate SQLs ----------
        n_samples = 5
        raw_outputs = self.llm(
            user_prompt,
            system=system_prompt,
            temperature=0.7,
            n=n_samples,
        )

        # Normalise LLM return into a list of strings
        if isinstance(raw_outputs, str):
            candidates_text = [raw_outputs]
        elif isinstance(raw_outputs, list):
            candidates_text = [str(x) for x in raw_outputs]
        else:
            candidates_text = [str(raw_outputs)]

        # Extract a clean SQL string from each candidate
        candidates: list[str] = []
        for text in candidates_text:
            sql = bridge.extract_sql(text)
            if sql and sql.strip():
                candidates.append(sql.strip())

        # Fall back to whatever we have if extraction failed for everything
        if not candidates:
            for text in candidates_text:
                if text and text.strip():
                    candidates.append(text.strip())
        if not candidates:
            return ""

        # ---------- 3. Execute each candidate ----------
        executed: list[tuple[str, dict]] = []
        for sql in candidates:
            try:
                result = self.execute(sql)
            except Exception as exc:  # defensive
                result = {"ok": False, "rows": [], "error": str(exc)}
            executed.append((sql, result))

        # ---------- 4. Vote among execution results ----------
        # We key on a canonicalised representation of the row set so identical
        # result tables collapse even if the SQL strings differ syntactically.
        def canonicalise(result: dict) -> Any:
            if not result.get("ok"):
                return ("ERROR", result.get("error", ""))
            rows = result.get("rows", [])
            try:
                normalised = json.dumps(rows, sort_keys=True, default=str)
            except TypeError:
                normalised = repr(rows)
            return ("OK", normalised)

        buckets: dict[Any, list[str]] = {}
        for sql, result in executed:
            key = canonicalise(result)
            buckets.setdefault(key, []).append(sql)

        # Prefer a non-error bucket if one exists.
        ordered_keys = sorted(
            buckets.keys(),
            key=lambda k: (0 if k[0] == "OK" else 1, -len(buckets[k])),
        )

        best_sql = buckets[ordered_keys[0]][0]

        # ---------- 5. Optional self-repair for the chosen winner ----------
        # If the winner is an error, try one quick repair pass.
        chosen_result = next(r for s, r in executed if s == best_sql)
        if not chosen_result.get("ok"):
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"The following SQL failed with this error:\n"
                f"{chosen_result.get('error', '')}\n\n"
                f"SQL:\n{best_sql}\n\n"
                "Return a corrected SQL statement and nothing else."
            )
            repaired_text = self.llm(
                repair_prompt,
                system=system_prompt,
                temperature=0.0,
                n=1,
            )
            if isinstance(repaired_text, list):
                repaired_text = repaired_text[0] if repaired_text else ""
            repaired_sql = bridge.extract_sql(repaired_text or "")
            if repaired_sql:
                try:
                    repaired_result = self.execute(repaired_sql)
                except Exception as exc:
                    repaired_result = {"ok": False, "rows": [], "error": str(exc)}
                if repaired_result.get("ok"):
                    best_sql = repaired_sql.strip()

        return best_sql