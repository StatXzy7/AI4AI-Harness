"""Execution-aware self-consistency voting: draw one greedy plus several perturbed SQL candidates, execute each, and return the candidate whose result is backed by the largest cluster of agreeing executions."""

# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G1(SQLHarness):
    """Wraps the frozen weak solver and upgrades its single greedy call with
    execution-aware majority voting:

    1. Ask the weak solver once greedily (temperature 0.0) -> anchor candidate.
    2. Draw NUM_SAMPLES extra candidates, rotating sampling temperatures and
       benign review hints so the candidate pool is genuinely diverse (this
       also keeps the vote alive even on a temperature-insensitive backend).
    3. Execute every distinct candidate against the database.
    4. Cluster the executable candidates by their execution result
       (row-count + leading rows). Each candidate casts one vote for its
       cluster; the most-voted cluster wins, with tie-breaks favouring
       non-empty results, the greedy anchor, and earliest proposal.
    5. If nothing executes, fall back to a plain textual majority vote over
       the proposed SQL strings (greedy answer wins ties).
    """

    NAME = "P2P2AGlmS1G1"

    #: extra perturbed samples drawn on top of the greedy anchor
    NUM_SAMPLES = 6
    #: temperatures rotated across the perturbed samples
    SAMPLE_TEMPERATURES = (0.6, 0.8, 1.0)
    #: number of leading rows used when fingerprinting an execution result
    FINGERPRINT_ROWS = 50

    _SYSTEM = (
        "You are an expert SQLite analyst. Translate the user's question into "
        "exactly one valid SQLite SELECT query that uses only the provided schema."
    )

    #: benign review nudges, rotated across the samples
    _HINTS = (
        "",
        "Before answering, double-check every JOIN condition.",
        "Before answering, re-read the question and make sure the WHERE clause filters exactly what is asked.",
        "Before answering, consider whether DISTINCT or GROUP BY is needed to avoid duplicate rows.",
        "Before answering, pay attention to aggregation functions and possible NULL values.",
        "Before answering, make sure the selected columns directly answer the question.",
    )

    _WRITE_PREFIXES = (
        "drop", "delete", "insert", "update", "alter", "create", "replace",
        "truncate", "attach", "detach", "pragma", "vacuum", "reindex",
    )

    # ------------------------------------------------------------------ #
    # prompt construction and candidate generation
    # ------------------------------------------------------------------ #
    def _prompt(self, question: str, hint: str = "") -> str:
        prompt = (
            "Database schema:\n"
            "%s\n\n"
            "Question: %s\n\n"
            "Task: write exactly one SQLite SELECT statement that answers the question.\n"
            "Rules:\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Output only a single