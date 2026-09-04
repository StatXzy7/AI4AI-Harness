"""Execution-guided self-consistency voting: draw multiple sampled SQL candidates from the frozen solver, execute every distinct read-only candidate against the database, and return the most frequently proposed query that runs cleanly."""

# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS0G4(SQLHarness):
    """Improvement over a single greedy generation: self-consistency voting
    with execution-based validation.

    Control flow per question:

      1. One greedy (temperature 0.0) generation anchors the candidate pool.
      2. ``N_SAMPLES`` additional generations are drawn at a non-zero
         temperature so the weak solver explores alternative readings of the
         question.
      3. Candidates are whitespace-normalised and deduplicated; each distinct
         candidate that is a single read-only statement (``SELECT`` / ``WITH``
         / ``VALUES`` / ``TABLE``) is executed once against the real database,
         and candidates whose execution errors are discarded.
      4. Among the executable candidates the winner is the one with the most
         votes (self-consistency). Ties break, in order, on: returns at least
         one row, matches the greedy anchor, was proposed earliest.
      5. If nothing executes, the greedy anchor is returned unvalidated
         (plurality candidate if the anchor is empty; ``""`` only if the
         solver produced nothing at all).
    """

    N_SAMPLES = 6                 # extra sampled candidates per question
    SAMPLE_TEMPERATURE = 0.7      # diversity for the sampled candidates
    MAX_EXECUTIONS = 8            # safety cap on distinct executions
    READ_ONLY_STARTS = ("SELECT", "WITH", "VALUES", "TABLE")

    SYSTEM = (
        "You are an expert SQLite data analyst. "
        "Reply with exactly one SQLite SELECT query and nothing else."
    )

    last_trace = None

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #
    def _prompt(self, question: str) -> str:
        schema = (getattr(self, "schema", None) or "").strip()
        question = (question or "").strip()
        return (
            "Database schema (SQLite DDL):\n"
            "------------------------------\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            "Task: write ONE SQLite query that answers the question.\n"
            "Rules:\n"
            "- Use only the tables and columns defined in the schema.\n"
            "- Emit a single read-only SELECT statement.\n"
            "- Output only the SQL, preferably in a