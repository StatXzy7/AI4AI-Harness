"""Harness that improves on single greedy generation via an execution-feedback repair loop: generate SQL, run it, and feed any execution error back to the frozen solver for regeneration until it runs or the attempt budget is exhausted."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS0G5(SQLHarness):
    MAX_ATTEMPTS = 3

    def _initial_prompt(self, question: str) -> str:
        return (
            "You are an expert SQLite query writer.\n"
            "Given the database schema below, write a single valid SQLite "
            "SQL query that answers the user's question.\n\n"
            "=== DATABASE SCHEMA ===\n"
            f"{self.schema}\n\n"
            "=== QUESTION ===\n"
            f"{question}\n\n"
            "Return ONLY the SQL query. No explanations, no markdown fences."
        )

    def _repair_prompt(self, question: str, bad_sql: str, error: str) -> str:
        return (
            "You are an expert SQLite query writer.\n"
            "A previously generated SQL query failed to execute against the "
            "database described below. Repair it.\n\n"
            "=== DATABASE SCHEMA ===\n"
            f"{self.schema}\n\n"
            "=== QUESTION ===\n"
            f"{question}\n\n"
            "=== FAILING SQL ===\n"
            f"{bad_sql}\n\n"
            "=== EXECUTION ERROR ===\n"
            f"{error}\n\n"
            "Diagnose the failure: check that every table and column name "
            "exists in the schema exactly as written, check quoting of "
            "string literals, join conditions, and aggregate usage. "
            "Then return ONLY the corrected single SQLite SQL query. "
            "No explanations, no markdown fences."
        )

    def solve(self, question: str) -> str:
        # Stage 1: greedy initial generation from the frozen solver.
        completion = self.llm(
            self._initial_prompt(question), system="", temperature=0.0, n=1
        )
        sql = bridge.extract_sql(completion) or completion.strip()

        # Stage 2: execution-feedback repair loop. The control flow is
        # driven by actually running the SQL: only errors that the database
        # itself reports are fed back for regeneration.
        for _attempt in range(self.MAX_ATTEMPTS):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "unknown execution error")
            repair_completion = self.llm(
                self._repair_prompt(question, sql, error),
                system="",
                temperature=0.0,
                n=1,
            )
            fixed_sql = bridge.extract_sql(repair_completion) or repair_completion.strip()

            # If the solver cannot produce a different query, further
            # identical repair calls would just repeat the same failure.
            if not fixed_sql or fixed_sql.strip() == sql.strip():
                break
            sql = fixed_sql

        # Return the best-effort query (last candidate) if the budget ran out.
        return sql