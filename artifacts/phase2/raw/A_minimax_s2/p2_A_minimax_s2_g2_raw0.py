"""Repair loop harness that executes candidate SQL and feeds errors back for regeneration."""
# MECHANISM: repair

import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G2(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: produce an initial SQL draft from the schema + question.
        initial_prompt = self._build_initial_prompt(question)
        initial_text = self.llm(initial_prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(initial_text)
        if not sql:
            return ""

        # Repair loop: execute, then if execution fails ask the LLM to repair using
        # the schema, original question, attempted SQL, and the database error.
        max_attempts = 3
        last_error = ""
        for attempt in range(max_attempts):
            result = self.execute(sql)
            if result.get("ok"):
                return sql
            last_error = result.get("error", "unknown error")
            if attempt == max_attempts - 1:
                break
            repair_prompt = self._build_repair_prompt(question, sql, last_error)
            repair_text = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            new_sql = bridge.extract_sql(repair_text)
            if not new_sql or self._normalize(new_sql) == self._normalize(sql):
                # No improvement possible; stop early to avoid looping.
                break
            sql = new_sql

        return sql

    def _build_initial_prompt(self, question: str) -> str:
        return (
            "You are a Text-to-SQL expert.\n"
            "Given the database schema below, write a single SQLite-compatible SQL query "
            "that answers the user's question. Return ONLY the SQL inside a