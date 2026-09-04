"""Execution-grounded self-consistency voting: draw several SQL candidates (a greedy anchor plus diverse samples), execute each one, and return the query whose result set wins the majority vote."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G0(SQLHarness):
    """Vote over multiple sampled SQL queries, grounded in real executions.

    Instead of a single greedy call, ``solve`` runs this control flow:

    1. Draw a greedy *anchor* candidate (the frozen solver's plain answer).
    2. Draw ``N_SAMPLES`` further candidates with varied instructions and a
       non-zero temperature, so the pool stays diverse even on deterministic
       backends.
    3. Execute every distinct candidate once (read-only queries only) and
       characterise each result by its row count plus the multiset of rows.
    4. Group candidates by result signature; a group's score is the summed
       frequency of every query producing that same result.
    5. Return the most frequent query inside the highest-scoring group (the
       greedy anchor breaks ties). If nothing executes, fall back to the
       anchor, so the harness is never worse than the plain solver.
    """

    SYSTEM = (
        "You are an expert data analyst. You answer with exactly one SQLite "
        "SELECT query, formatted exactly as requested."
    )

    N_SAMPLES = 4       # diverse samples drawn on top of the greedy anchor
    TEMPERATURE = 0.7   # sampling temperature for the non-anchor candidates
    SIG_ROW_CAP = 200   # rows of a result used when comparing result sets

    # Statements that do not start with SELECT/WITH, contain a second
    # statement, or contain one of these words are never executed; they
    # simply receive no vote.
    _WRITE_KEYWORDS = (
        "insert", "update", "delete", "drop", "alter", "create",
        "attach", "detach", "pragma", "vacuum", "reindex",
    )

    _VARIANTS = (
        "Write ONE SQLite SELECT statement that answers the question. Use only "
        "tables and columns that appear in the schema. Reply with the query in "
        "a single