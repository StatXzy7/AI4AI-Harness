"""Repairs SQL in a bounded loop by executing each candidate and feeding execution errors back to the LLM for regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G2(SQLHarness):
    """Greedy Text-to-SQL generation followed by execution-guided self-repair."""

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL system. Given a database schema and a "
            "natural-language question you produce one valid SQLite query. "
            "Output only SQL: no prose, no markdown fences."
        )
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite query that answers the question, using only "
            "tables and columns that appear in the schema."
        )

        failures = []  # (sql, error) pairs that failed execution
        sql = ""
        for _ in range(self.MAX_ATTEMPTS):
            if failures:
                history = "\n\n".join(
                    f"Attempt {i} SQL:\n{bad}\nExecution error: {err}"
                    for i, (bad, err) in enumerate(failures, start=1)
                )
                prompt = (
                    f"{base_prompt}\n\n"
                    "The following attempts failed when executed against the "
                    "database:\n"
                    f"{history}\n\n"
                    "Rewrite the query so it executes successfully and answers the "
                    "question. Do not repeat any failed query verbatim. Output only "
                    "the corrected SQL."
                )
            else:
                prompt = base_prompt

            text = self.llm(prompt, system=system, temperature=0.0, n=1)
            if isinstance(text, (list, tuple)):
                text = text[0] if text else ""

            candidate = bridge.extract_sql(text)
            if candidate:
                sql = candidate
            elif not sql:
                sql = text.strip()

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = str(result.get("error") or "unknown execution error")
            failures.append((sql, error))

        return sql