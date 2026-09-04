"""Harness that generates SQL greedily, executes it, and on failure feeds the SQLite error back into the prompt for iterative repair until the query runs or attempts run out."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS0G4(SQLHarness):
    """Greedy generation + execution-feedback repair loop.

    Improvement over a single greedy call: instead of returning the first
    generated query blindly, the harness executes it against the database.
    If SQLite reports an error, the failing SQL and the exact error message
    are appended to the prompt and the model is asked to produce a corrected
    query. This repeats for up to MAX_ATTEMPTS rounds. The first query that
    executes successfully is returned; otherwise the last candidate is
    returned as a best-effort fallback.
    """

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite text-to-SQL assistant. Given a database "
            "schema and a natural-language question, you write a single valid "
            "SQLite query. You output only the SQL query itself: no prose, no "
            "explanations, no markdown fences."
        )

        base_prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite SQL query that answers the question. "
            "Use only tables and columns that appear in the schema. "
            "Output only the SQL query."
        )

        prompt = base_prompt
        last_sql = ""

        for attempt in range(self.MAX_ATTEMPTS):
            # First attempt is fully deterministic; later repairs get a small
            # temperature so the model can escape repeated identical mistakes.
            temperature = 0.0 if attempt == 0 else 0.3
            response = self.llm(prompt, system=system, temperature=temperature)
            sql = bridge.extract_sql(response)

            if not sql:
                # The model produced no extractable SQL; demand a bare query.
                prompt = (
                    base_prompt
                    + "\n\nYour previous reply contained no SQL query. "
                    "Respond with exactly one SQL statement and nothing else."
                )
                continue

            last_sql = sql
            result = self.execute(sql)

            if result.get("ok"):
                return sql

            error = result.get("error", "unknown error")
            prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"This SQL query failed to execute:\n