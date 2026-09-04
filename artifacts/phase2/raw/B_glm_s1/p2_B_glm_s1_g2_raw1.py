"""Draw one greedy plus several stochastic SQL candidates from the frozen solver and select the final query by execution-aware majority vote."""

# MECHANISM: vote

from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2BGlmS1G2"]


class P2P2BGlmS1G2(SQLHarness):
    """Self-consistency harness for a frozen weak text-to-SQL solver.

    Instead of trusting a single greedy generation, the harness draws one
    greedy "anchor" candidate plus several temperature samples, executes every
    distinct candidate once, and elects the winner by majority vote over
    execution-equivalence classes (candidates whose queries return identical
    result sets pool their votes). Candidates that fail to execute are
    excluded from the election; if none execute, a plain textual plurality
    vote is used.
    """

    NAME = "P2P2BGlmS1G2"

    #: number of stochastic samples drawn in addition to the greedy anchor
    N_SAMPLES = 5
    #: temperature for the stochastic samples (the greedy anchor uses 0.0)
    SAMPLE_TEMPERATURE = 0.7
    #: max number of rows used when fingerprinting an execution result
    SIGNATURE_ROW_CAP = 1000

    SYSTEM = (
        "You are an expert text-to-SQL translator. Given a database schema and "
        "a natural-language question, write exactly one SQLite SELECT query "
        "that answers the question."
    )

    # ------------------------------------------------------------------ prompt
    def _prompt(self, question: str) -> str:
        schema = (getattr(self, "schema", "") or "").strip()
        return (
            "Database schema:\n"
            "----------------\n"
            f"{schema}\n"
            "----------------\n\n"
            f"Question: {(question or '').strip()}\n\n"
            "Task: write one SQLite SQL query that answers the question.\n"
            "Rules:\n"
            "1. Use only tables and columns that appear in the schema above.\n"
            "2. Output exactly one SQL statement (a single SELECT query).\n"
            "3. Use portable SQLite syntax only.\n"
            "4. Put the final query in a