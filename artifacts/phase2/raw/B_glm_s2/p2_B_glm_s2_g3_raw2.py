"""Greedy SQL generation refined by an execution-repair loop: each candidate query is run against the database and, when it fails, the exact execution error is fed back to the solver for up to three correction rounds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G3(SQLHarness):
    """Text-to-SQL harness: generate, execute, and repair on failure."""

    MAX_ROUNDS = 3
    FALLBACK_SQL = "SELECT 1;"

    def _build_prompt(self, question: str, history) -> str:
        """Compose the prompt; when `history` is non-empty it carries the
        (failed_sql, error) pairs from earlier rounds so the solver can repair."""
        parts = [
            "You are an expert SQLite assistant.",
            "Using the schema below, write exactly one SQL query that answers the question.",
            "",
            "### Schema",
            self.schema,
            "",
            "### Question",
            question,
            "",
        ]
        if history:
            parts.append(
                "Your previous attempts failed to execute on the database. "
                "Study each failure below and produce a corrected query."
            )
            parts.append("")
            for idx, (sql, err) in enumerate(history, start=1):
                parts.append(f"Attempt {idx}:")
                parts.append(sql.strip() if sql.strip() else "(no SQL produced)")
                parts.append(f"Execution error: {err}")
                parts.append("")
            parts.append(
                "Return a single corrected SQL query in a