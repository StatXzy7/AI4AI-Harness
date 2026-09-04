"""Repair-loop Text-to-SQL harness that executes each generated query and feeds database errors back to the LLM until the SQL runs or the attempt budget runs out."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS0G0(SQLHarness):
    """Generate-and-repair Text-to-SQL solver.

    Control flow (a real repair loop, not a single greedy call):
      1. Prompt the frozen LLM with the schema and question to get a
         candidate SQL query.
      2. Extract the SQL with bridge.extract_sql and execute it against
         the database.
      3. If execution succeeds, return the query immediately.
      4. If execution fails, record the (SQL, error) pair in a failure
         history and re-prompt the LLM with that feedback so it can
         correct the mistake instead of repeating it.
      5. If the attempt budget is exhausted, return the best-effort
         candidate produced along the way.
    """

    MAX_ATTEMPTS = 4

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL translator for SQLite databases. "
        "Given a database schema and a natural-language question, you write "
        "one correct SQLite SELECT query. You output only SQL, never "
        "explanations. When you are shown a query that failed together with "
        "the database error message, you diagnose the cause and output a "
        "fixed query rather than repeating the mistake."
    )

    # ---------- prompt construction ----------

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SELECT query that answers the question. "
            "Output only the SQL."
        )

    def _repair_prompt(self, question: str, failures: list) -> str:
        parts = [
            "Database schema:",
            self.schema,
            "",
            f"Question: {question}",
            "",
            "Every attempt so far failed to execute. Study the error "
            "messages, identify what was wrong (table or column names, "
            "syntax, joins, clauses), and write one corrected SQLite "
            "SELECT query. Do not repeat a previous query verbatim.",
            "",
        ]
        for i, (sql, error) in enumerate(failures, start=1):
            parts.append(f"--- Attempt {i} ---")
            parts.append("SQL that failed:")
            parts.append(f"