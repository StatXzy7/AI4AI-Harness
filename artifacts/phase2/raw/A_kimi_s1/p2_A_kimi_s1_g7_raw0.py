"""Execution-feedback repair harness: generate SQL greedily, execute it, and feed real database errors back into the frozen solver for bounded regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS1G7(SQLHarness):
    """Generate -> execute -> repair loop.

    The frozen solver first produces a greedy SQL draft. The harness then
    executes it against the live database; whenever execution fails, the
    concrete error message and the faulty SQL are fed back into the solver
    with an explicit diagnosis-and-correction instruction. The loop runs for
    at most MAX_ATTEMPTS executions and returns the first query that runs
    cleanly, or the last candidate if none succeed.
    """

    SYSTEM = (
        "You are an expert SQLite query writer. Given a database schema and a "
        "natural-language question, produce exactly one correct SQLite SELECT "
        "query. Output only the SQL query, with no explanations and no markdown "
        "fences."
    )

    MAX_ATTEMPTS = 3

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SELECT statement that answers the question."
        )

    def _repair_prompt(self, question: str, bad_sql: str, error: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "A previous attempt produced this SQL query:\n"
            f"{bad_sql}\n\n"
            "Executing it against the database failed with this error:\n"
            f"{error}\n\n"
            "Diagnose the root cause (for example: a misspelled or nonexistent "
            "table/column name, invalid SQLite syntax, an ambiguous column, a "
            "bad join condition, or a type mismatch), then write a corrected "
            "single SQLite SELECT statement that answers the question. Output "
            "only the corrected SQL."
        )

    def _generate(self, prompt: str) -> str:
        raw = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)
        if not sql:
            sql = (raw or "").strip()
        return sql

    def solve(self, question: str) -> str:
        sql = self._generate(self._initial_prompt(question))

        for attempt in range(self.MAX_ATTEMPTS):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            if attempt == self.MAX_ATTEMPTS - 1:
                break

            error = result.get("error") or "unknown execution error"
            repaired = self._generate(self._repair_prompt(question, sql, error))
            if repaired:
                sql = repaired

        return sql