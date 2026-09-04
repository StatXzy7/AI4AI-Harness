"""Text-to-SQL harness that repairs its SQL by executing each candidate and feeding errors/empty results back into the LLM for regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G3(SQLHarness):
    MAX_ATTEMPTS = 4

    def _initial_prompt(self, question: str) -> str:
        return (
            "You are given the following database schema:\n"
            f"{self.schema}\n\n"
            "Write a single SQLite SQL query that answers the question below. "
            "Output ONLY the SQL query, no explanation, no markdown fences.\n\n"
            f"Question: {question}\n"
            "SQL:"
        )

    def _repair_prompt(self, question: str, bad_sql: str, feedback: str) -> str:
        return (
            "You are given the following database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "A previous attempt to answer this question used this SQL query:\n"
            f"{bad_sql}\n\n"
            f"That attempt failed as follows:\n{feedback}\n\n"
            "Diagnose the problem (check table/column names against the schema, "
            "join conditions, filter values, aggregation, and SQLite syntax) and "
            "write a corrected single SQLite SQL query. "
            "Output ONLY the corrected SQL query, no explanation, no markdown fences.\n\n"
            "SQL:"
        )

    def solve(self, question: str) -> str:
        # Attempt 1: fresh greedy generation.
        response = self.llm(self._initial_prompt(question), temperature=0.0)
        candidate = bridge.extract_sql(response)

        first_ok_sql = None  # fallback: first query that executed successfully

        for attempt in range(self.MAX_ATTEMPTS):
            if not candidate:
                feedback = "No SQL query was produced. You must output a SQL query."
            else:
                result = self.execute(candidate)
                if result.get("ok"):
                    rows = result.get("rows") or []
                    if first_ok_sql is None:
                        first_ok_sql = candidate
                    if rows:
                        # Executed and returned data: accept immediately.
                        return candidate
                    feedback = (
                        "The query executed successfully but returned ZERO rows. "
                        "This usually means a filter value does not match the data "
                        "(check exact string values, use LIKE where appropriate), a "
                        "join is too restrictive, or a WHERE condition is wrong. "
                        "Relax or correct the conditions so the query returns rows."
                    )
                else:
                    feedback = (
                        "Executing the query produced this database error:\n"
                        f"{result.get('error', 'unknown error')}\n"
                        "Fix the SQL so it runs without errors."
                    )

            # Last attempt already consumed: stop instead of generating again.
            if attempt == self.MAX_ATTEMPTS - 1:
                break

            # Feed the failure back and regenerate.
            response = self.llm(
                self._repair_prompt(question, candidate or "(none)", feedback),
                temperature=0.0,
            )
            new_candidate = bridge.extract_sql(response)
            if new_candidate:
                candidate = new_candidate

        # Never got a non-empty result: prefer a query that at least executed.
        if first_ok_sql is not None:
            return first_ok_sql
        return candidate or "SELECT 1"