"""Text-to-SQL harness with an execution-error repair loop: generated SQL is run against the database and any error is fed back to the LLM to regenerate a corrected query, up to a bounded number of attempts."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G1(SQLHarness):
    """Repair-loop harness.

    Control flow:
      1. Greedy-generate an initial SQL query from schema + question.
      2. Execute it against the database.
      3. If execution succeeds, return the SQL immediately.
      4. If execution fails, build a repair prompt containing the failing SQL
         and the exact execution error, regenerate, and retry.
      5. Repeat until success or the attempt budget is exhausted; return the
         most recent candidate (best effort) if all attempts fail.
    """

    MAX_ATTEMPTS = 4  # 1 initial generation + up to 3 error-driven repairs

    SYSTEM = (
        "You are an expert SQLite developer. You write correct, minimal, "
        "executable SQL queries and repair broken ones when given error messages."
    )

    def _initial_prompt(self, question: str) -> str:
        return (
            "Given the database schema below, write a single SQL query that "
            "answers the question.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Rules:\n"
            "- Use only tables and columns present in the schema.\n"
            "- Return ONLY the SQL query: no explanation, no markdown fences."
        )

    def _repair_prompt(self, question: str, bad_sql: str, error: str) -> str:
        return (
            "A SQL query you wrote failed to execute. Diagnose the cause from "
            "the error message and produce a corrected query.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Failing SQL:\n{bad_sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Rules:\n"
            "- Fix the specific problem reported by the error (e.g. unknown "
            "table/column names, syntax errors, ambiguous columns).\n"
            "- Use only tables and columns present in the schema.\n"
            "- Return ONLY the corrected SQL query: no explanation, no markdown "
            "fences."
        )

    def _generate(self, prompt: str) -> str:
        """Call the frozen solver and extract a clean SQL string."""
        text = self.llm(prompt, system=self.SYSTEM, temperature=0.0)
        sql = bridge.extract_sql(text)
        return sql.strip() if isinstance(sql, str) else ""

    def solve(self, question: str) -> str:
        sql = self._generate(self._initial_prompt(question))

        for _ in range(self.MAX_ATTEMPTS):
            if not sql:
                # Nothing executable was produced; regenerate from scratch.
                sql = self._generate(self._initial_prompt(question))
                if not sql:
                    continue

            result = self.execute(sql)

            if result.get("ok"):
                return sql

            # Execution failed: feed the error back and ask for a fix.
            error = result.get("error") or "unknown execution error"
            fixed = self._generate(self._repair_prompt(question, sql, error))

            if not fixed or fixed == sql:
                # No progress possible from this repair step; stop early and
                # return the best (failing) candidate we have.
                break
            sql = fixed

        return sql