"""Draws several SQL candidates from the frozen solver and elects the final query by majority vote over clusters of identical execution results."""
# MECHANISM: vote

from collections import defaultdict

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G3(SQLHarness):
    """Execution-aware self-consistency voting around the frozen weak solver.

    Control flow per question (a real change over a single greedy call):

      1. DRAW: one greedy anchor sample plus N perturbed samples
         (temperature > 0, rotating instruction hints) from the frozen solver.
      2. VALIDATE: extract + normalize each candidate SQL, execute each
         distinct candidate once against the database.
      3. VOTE: cluster the executable candidates by an order-insensitive
         fingerprint of their result rows and elect the cluster with the most
         votes (ties: prefer non-empty results, then earlier samples).
      4. RETURN: within the winning cluster, the most frequently proposed SQL
         text; if nothing executes at all, a plain majority vote over the
         proposed SQL texts.
    """

    N_SAMPLES = 5
    SAMPLE_TEMPERATURE = 0.8
    MAX_FP_ROWS = 100
    _QUERY_PREFIXES = ("select", "with", "values", "pragma", "explain")

    _SYSTEM = (
        "You are a careful text-to-SQL engine. Given a database schema and a "
        "natural-language question, you output exactly one SQL query."
    )

    _PROMPT = (
        "Database schema:\n{schema}\n\n"
        "Question: {question}\n\n"
        "Write one SQL query (SQLite dialect) that answers the question. "
        "Put the query in a