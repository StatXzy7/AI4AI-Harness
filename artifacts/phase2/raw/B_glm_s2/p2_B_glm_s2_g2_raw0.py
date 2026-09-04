"""Draws several sampled SQL candidates for a question and majority-votes among them, using execution success as a validity filter before counting ballots."""
# MECHANISM: vote

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G2(SQLHarness):
    """Multi-sample voting harness around a frozen weak Text-to-SQL solver.

    Control flow (a real change vs. a single greedy call):
      1. One greedy anchor sample (temperature 0.0) plus N-1 stochastic samples
         (temperature > 0) are drawn from the same frozen solver.
      2. Every sample is SQL-extracted and bucketed by a normalized form of the
         query, so identical queries pool their votes.
      3. Each *unique* candidate is executed once against the database; only
         candidates that execute cleanly are eligible to win.
      4. The winner is the execution-valid candidate with the highest vote
         count (ties broken toward the earliest-seen candidate, which favors
         the greedy anchor). If nothing executes, the overall plurality
         candidate is returned as a fallback.
    """

    NAME = "P2P2BGlmS2G2"

    N_SAMPLES = 5              # total candidates (1 greedy + 4 sampled)
    SAMPLE_TEMPERATURE = 0.9   # temperature for the stochastic samples

    SYSTEM = (
        "You are an expert SQLite data analyst. You answer with exactly one "
        "SQL query and nothing else."
    )

    def _prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite SELECT statement that answers the question.\n"
            "Rules:\n"
            "- Use only the tables and columns shown in the schema above.\n"
            "- Put the query inside a