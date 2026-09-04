"""Repair-loop harness: generate a candidate SQL greedily, execute it against the database, and, when execution fails, feed the engine error plus the full failure history back to the frozen solver for bounded corrective regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2AGlmS0G4"]


class P2P2AGlmS0G4(SQLHarness):
    """Text-to-SQL harness with an execution-driven repair loop.

    Control flow (a real change over a single greedy call):

        1. Ask the frozen solver for one SQL query (greedy, temperature 0.0).
        2. Execute the extracted query on the target database.
        3. If execution fails (engine error, or nothing extractable at all),
           build a repair prompt that contains the schema, the question, every
           failed query so far, and the exact error message produced by the
           engine, then ask the frozen solver to regenerate.
        4. Repeat up to ``MAX_ATTEMPTS`` rounds.
        5. Return the first query that executes cleanly; if none does, return
           the most recently repaired non-empty candidate.
    """

    MAX_ATTEMPTS = 3

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL translator for SQLite. "
        "You reply with exactly one SQL query and nothing else."
    )

    # ------------------------------ prompts ------------------------------ #

    @property
    def _schema_text(self) -> str:
        schema = getattr(self, "schema", None)
        if isinstance(schema, str):
            return schema
        if schema is None:
            return ""
        return str(schema)

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            "----------------\n"
            f"{self._schema_text}\n"
            "\n"
            "Question:\n"
            "---------\n"
            f"{question}\n"
            "\n"
            "Write exactly one SQLite SELECT query that answers the question.\n"
            "Guidelines:\n"
            "1. Use only tables and columns that appear verbatim in the schema above.\n"
            "2. Join tables with explicit JOIN ... ON conditions on the correct keys.\n"
            "3. Put single quotes around text literals.\n"
            "4. Use SQLite syntax (LIMIT n OFFSET m, not TOP).\n"
            "5. Output ONLY the query inside a