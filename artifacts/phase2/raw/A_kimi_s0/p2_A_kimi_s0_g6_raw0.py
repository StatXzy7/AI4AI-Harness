"""Execution-feedback repair harness: generate SQL, run it, and feed errors back for bounded regeneration."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS0G6(SQLHarness):
    """Generate SQL greedily, execute it, and repair via error feedback.

    Control flow:
      1. One greedy generation from schema + question.
      2. Execute the candidate. If it runs and returns rows, accept it.
      3. If it raises an execution error (or returns zero rows on the first
         attempt), build a repair prompt containing the failed SQL plus the
         database's error message, and regenerate with mild temperature so the
         model does not repeat the identical mistake.
      4. Stop early if the same error string repeats (the model is stuck) and
         fall back to the best candidate seen so far.
    """

    MAX_ATTEMPTS = 4

    def _initial_prompt(self, question: str) -> str:
        return (
            "You are given the following database schema:\n"
            f"{self.schema}\n\n"
            "Write a single SQL query that answers the question below.\n"
            "Rules:\n"
            "- Output ONLY the SQL query, no explanation, no markdown fences.\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Qualify columns with table names when joining.\n\n"
            f"Question: {question}\n"
            "SQL:"
        )

    def _repair_prompt(self, question: str, bad_sql: str, error: str) -> str:
        return (
            "You are given the following database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "The following SQL query was attempted but the database rejected "
            "it:\n"
            f"