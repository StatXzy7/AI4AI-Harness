"""Execution-grounded voting: draw several candidates from the frozen solver, execute each against the database, and return the query whose canonical result set earns the most generation-weighted votes."""
# MECHANISM: vote

from typing import Any, Dict, List

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G5(SQLHarness):
    """Self-consistency over execution results.

    Control flow (a real change over a single greedy call):

    1. Sample the weak solver NUM_STOCHASTIC + 1 times (one greedy seed at
       temperature 0 plus stochastic draws at TEMPERATURE).
    2. Extract and deduplicate the candidate SQL statements, keeping track of
       how many samples produced each distinct candidate (its weight).
    3. Execute every distinct candidate against the real database and
       fingerprint the result rows into a canonical signature (order-insensitive,
       type-normalised, row-count aware).
    4. Cluster executing candidates by signature; each cluster's score is the
       total generation weight of its members. The winning cluster's
       highest-weight member is returned.

    Ties prefer non-empty result sets, then earlier candidates. If no candidate
    executes, the most frequently generated (read-only preferred) candidate is
    returned; if extraction fails entirely, the greedy seed's SQL is returned.
    """

    NAME = "P2P2BGlmS2G5"

    NUM_STOCHASTIC = 4   # extra samples drawn at TEMPERATURE
    TEMPERATURE = 0.8    # sampling temperature for the extra draws
    MAX_SIG_ROWS = 200   # rows considered when fingerprinting a result set

    SYSTEM = (
        "You are a precise text-to-SQL engine. "
        "Given a schema and a question, output exactly one SQL query."
    )

    # ------------------------------------------------------------------ #
    # prompting
    # ------------------------------------------------------------------ #
    def _prompt(self, question: str) -> str:
        schema = (getattr(self, "schema", "") or "").strip() or "(no schema provided)"
        return (
            "Write ONE SQL query that answers the question using the database schema below.\n"
            "\n"
            "Schema:\n"
            f"{schema}\n"
            "\n"
            "Rules:\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Emit a single SELECT statement, no explanations.\n"
            "- Wrap the query in a