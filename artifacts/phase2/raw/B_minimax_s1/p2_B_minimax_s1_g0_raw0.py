# MECHANISM: repair
"""Repair-on-error: execute candidate SQL, feed execution failures back to LLM for one revision pass."""
from __future__ import annotations
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS1G0(SQLHarness):
    def solve(self, question: str) -> str:
        # First pass: greedy generation
        prompt1 = (
            "You are a Text-to-SQL expert. Given the database schema and a natural language "
            "question, produce a single SQLite-compatible SQL query that answers the question.\n\n"
            "Schema:\n"
            f"{self.schema}\n\n"
            "Question:\n"
            f"{question}\n\n"
            "Return ONLY the SQL statement, with no prose, no markdown fences, and no "
            "explanation. Do not prefix with labels like 'SQL:'."
        )
        raw1 = self.llm(prompt1, system="", temperature=0.0, n=1)
        sql1 = bridge.extract_sql(raw1)
        if not sql1:
            return ""

        # Execute the first attempt
        result = self.execute(sql1)
        if result.get("ok"):
            return sql1

        # Repair pass: feed the error back to the LLM
        err = result.get("error", "unknown error")
        # Truncate very long error messages so the prompt stays bounded
        if isinstance(err, str) and len(err) > 1200:
            err = err[:1200] + " ..."
        prompt2 = (
            "You are a Text-to-SQL expert. A previous SQL query you produced failed at "
            "execution time. Your job is to FIX the query so it runs successfully against "
            "the given database and answers the original question.\n\n"
            "Schema:\n"
            f"{self.schema}\n\n"
            "Question:\n"
            f"{question}\n\n"
            "Previous SQL (may be malformed or semantically wrong):\n"
            f"{sql1}\n\n"
            "Database execution error reported:\n"
            f"{err}\n\n"
            "Return ONLY the corrected SQL statement, with no prose, no markdown fences, "
            "and no explanation. Do not prefix with labels like 'SQL:'."
        )
        raw2 = self.llm(prompt2, system="", temperature=0.0, n=1)
        sql2 = bridge.extract_sql(raw2)
        if not sql2:
            # Repair produced nothing usable; fall back to the first attempt so callers
            # still get a non-empty string (execution can be inspected by the caller).
            return sql1

        result2 = self.execute(sql2)
        if result2.get("ok"):
            return sql2

        # Repair still failing: return the best static candidate (the repaired one),
        # since it was at least informed by the execution error.
        return sql2