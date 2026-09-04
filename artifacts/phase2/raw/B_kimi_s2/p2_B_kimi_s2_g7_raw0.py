"""Iterative SQL repair harness: generate, execute, and feed SQLite errors back to the LLM until the query runs or attempts are exhausted."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G7(SQLHarness):
    """Repair-loop harness.

    A single greedy generation is fragile: a weak solver often picks a wrong
    column name, mis-nests an aggregate, or emits dialect-invalid SQL. This
    harness closes the loop with the database: every candidate query is
    executed, and any SQLite error is appended to the prompt as explicit
    feedback so the next generation can correct the concrete mistake instead
    of guessing blindly. The loop stops at the first query that executes
    successfully, or after MAX_ATTEMPTS tries, in which case the most recent
    syntactically-extractable query is returned.
    """

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite text-to-SQL engine. Given a database "
            "schema and a natural-language question, produce ONE valid SQLite "
            "query that answers it. Output ONLY the SQL query: no explanation, "
            "no markdown fences, no comments."
        )
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SQL query that answers the question."
        )

        feedback = ""
        last_sql = ""

        for attempt in range(self.MAX_ATTEMPTS):
            prompt = base_prompt + feedback
            # Stay greedy on the first try; allow a little exploration on
            # retries so the model can escape a repeated mistake.
            temperature = 0.0 if attempt == 0 else 0.3
            raw = self.llm(prompt, system=system, temperature=temperature)
            sql = bridge.extract_sql(raw)

            if not sql:
                feedback += (
                    "\n\nYour previous response contained no extractable SQL "
                    "query. Respond with ONLY the SQL query itself."
                )
                continue

            last_sql = sql
            result = self.execute(sql)

            if result.get("ok"):
                return sql

            error = result.get("error", "unknown execution error")
            feedback += (
                f"\n\nYour previous SQL query:\n{sql}\n"
                f"failed to execute. SQLite reported:\n{error}\n"
                "Repair the query. Check that every table and column name "
                "exists in the schema above, that JOIN keys are correct, and "
                "that the SQL is valid SQLite syntax. Respond with ONLY the "
                "corrected SQL query."
            )

        return last_sql