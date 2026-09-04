"""Generate SQL with the frozen solver, execute it, and on failure feed the exact SQLite error back into the prompt to regenerate, up to 2 repair attempts."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2Repair(SQLHarness):
    """Execution-guided repair harness for Text-to-SQL.

    Control flow:
      1. Ask the frozen LLM for a SQL query given the schema and question.
      2. Execute the candidate via ``self.execute``.
      3. If execution succeeds, return that SQL immediately.
      4. Otherwise, build a repair prompt containing the failed SQL and the
         *exact* SQLite error message, regenerate, and execute the new query.
      5. Allow at most ``MAX_REPAIRS`` (= 2) regenerations; if none execute
         successfully, return the last generated SQL as a best effort.
    """

    MAX_REPAIRS = 2

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL engine for SQLite. "
        "Given a database schema and a natural-language question, you write "
        "one correct SQLite query. You output only the SQL, with no "
        "explanation and no markdown."
    )

    def _generate(self, prompt: str) -> str:
        """Query the frozen LLM and extract a SQL string from its output."""
        response = self.llm(
            prompt,
            system=self.SYSTEM_PROMPT,
            temperature=0.0,
            n=1,
        )
        sql = bridge.extract_sql(response)
        if not sql:
            sql = (response or "").strip()
        return sql

    def solve(self, question: str) -> str:
        context = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n"
        )

        # 1) Initial generation.
        initial_prompt = (
            context
            + "\nWrite a single SQLite query that answers the question. "
            "Return only the SQL."
        )
        sql = self._generate(initial_prompt)

        # 2) Execute, then repair with exact error feedback up to MAX_REPAIRS times.
        result = self.execute(sql)
        repairs = 0
        while not result.get("ok", False) and repairs < self.MAX_REPAIRS:
            error = result.get("error") or "Unknown SQLite error."
            repair_prompt = (
                context
                + "\nThe following SQL query was generated:\n"
                f"{sql}\n\n"
                "It failed to execute. The exact SQLite error was:\n"
                f"{error}\n\n"
                "Fix the query so it executes successfully and still answers "
                "the question. Return only the corrected SQL."
            )
            sql = self._generate(repair_prompt)
            result = self.execute(sql)
            repairs += 1

        # 3) First SQL that executed successfully, else the last attempt (best effort).
        return sql