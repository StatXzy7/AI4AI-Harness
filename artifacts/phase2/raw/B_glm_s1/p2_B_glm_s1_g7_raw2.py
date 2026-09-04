"""Repair-loop harness: the frozen solver's SQL is executed, and engine errors are fed back for corrective regeneration."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G7(SQLHarness):
    """Execute-then-repair wrapper around the frozen weak solver.

    Instead of a single greedy generation, the control flow is:

      1. ask the frozen LLM for one SQL statement for the question;
      2. execute that statement against the database via ``self.execute``;
      3. if the engine reports an error, re-prompt the frozen LLM showing the
         failing statement and the verbatim engine error, then execute the fix;
      4. repeat for up to ``max_attempts`` rounds, returning the first
         statement the engine accepts, or the least-bad failure otherwise.
    """

    max_attempts = 4  # 1 initial generation + up to 3 repair rounds

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalize(sql: str) -> str:
        """Canonical form used to detect a stuck, repeating solver."""
        return " ".join(sql.strip().lower().split()).rstrip(";")

    def _execute(self, sql: str) -> dict:
        """Run SQL defensively; never let an engine crash kill the loop."""
        try:
            result = self.execute(sql)
        except Exception as exc:  # engine raised instead of reporting
            result = {"ok": False, "rows": [], "error": "exception: %s" % exc}
        if not isinstance(result, dict):
            result = {"ok": False, "rows": [], "error": "unexpected engine result"}
        result.setdefault("ok", False)
        result.setdefault("rows", [])
        result.setdefault("error", "")
        return result

    def _base_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            "%s\n\n"
            "Question: %s\n\n"
            "Write exactly one SQL query (a single SELECT statement) that "
            "answers the question. Use only tables and columns that appear "
            "in the schema. Output the query inside a