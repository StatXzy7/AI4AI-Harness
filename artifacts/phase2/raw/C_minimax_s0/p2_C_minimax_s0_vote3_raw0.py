"""Harness that generates 3 SQL candidates via the weak solver, executes parseable ones, and returns the majority-voted result."""
from __future__ import annotations

import re
from collections import Counter
from typing import List, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS0Vote3(SQLHarness):
    """Prompt the frozen solver 3 times (n=3, T=0.7), execute parseable SQL, and return the majority result."""

    SYSTEM_PROMPT = (
        "You are a Text-to-SQL assistant. Given a natural language question and a database schema, "
        "produce exactly one valid SQL query that answers the question. Output only the SQL, with no "
        "explanation, no markdown fences, and no commentary."
    )

    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""

        # Step 1: ask the frozen weak solver for 3 independent attempts.
        raw_outputs: List[str] = self.llm(
            prompt=question,
            system=self.SYSTEM_PROMPT,
            temperature=0.7,
            n=3,
        )
        if isinstance(raw_outputs, str):
            raw_outputs = [raw_outputs]

        # Step 2: extract a parseable SQL string from each attempt.
        candidates: List[str] = []
        for raw in raw_outputs:
            sql = bridge.extract_sql(raw or "")
            if sql:
                sql = self._clean_sql(sql)
                if sql:
                    candidates.append(sql)

        if not candidates:
            return ""

        # Step 3: execute everything that parses. Group by successful result payload.
        # A "result" is a hashable signature of the returned rows; the SQL whose result
        # appears most often wins.
        result_to_sqls: Counter = Counter()
        sql_to_results: List[Tuple[str, tuple]] = []
        for sql in candidates:
            outcome = self.execute(sql)
            if not outcome or not outcome.get("ok"):
                continue
            rows = outcome.get("rows") or []
            try:
                sig = self._row_signature(rows)
            except Exception:
                continue
            result_to_sqls[sig] += 1
            sql_to_results.append((sql, sig))

        if not sql_to_results:
            # Nothing executed cleanly: fall back to the first parseable candidate.
            return candidates[0]

        # Pick the signature with the highest count; break ties by first occurrence.
        winner_sig: tuple | None = None
        winner_count = -1
        for sig, sql in sql_to_results:
            if result_to_sqls[sig] > winner_count:
                winner_count = result_to_sqls[sig]
                winner_sig = sig

        for sql, sig in sql_to_results:
            if sig == winner_sig:
                return sql

        return candidates[0]

    @staticmethod
    def _clean_sql(sql: str) -> str:
        sql = sql.strip()
        # Strip common markdown fence wrappers defensively.
        sql = re.sub(r"^