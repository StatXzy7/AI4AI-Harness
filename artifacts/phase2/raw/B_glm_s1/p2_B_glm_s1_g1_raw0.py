"""Greedy text-to-SQL generation hardened by an execution-feedback repair loop: each candidate is executed against the database, and any execution error is fed back into the prompt to drive regeneration of a corrected query (bounded number of rounds)."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G1(SQLHarness):
    """
    Weak-solver wrapper that improves on a single greedy call with an
    execution-guided repair loop.

    Control flow per question:
      1. Greedily generate a candidate SQL conditioned on the schema.
      2. Execute the candidate on the frozen database.
      3. If execution fails, build a *repair* prompt that contains the exact
         failing SQL plus the exact database error, and ask the LLM to
         regenerate a corrected query.
      4. Repeat up to MAX_ROUNDS total generations. Return the first candidate
         that executes cleanly; otherwise return the last candidate seen
         (best effort).

    Notes:
      * An empty result set is NOT treated as failure -- an empty answer can
        be the correct answer; only hard execution errors trigger repair.
      * If a repair round reproduces the exact SQL that just failed, the loop
        stops early: with greedy decoding an identical prompt cannot yield a
        different query, so further rounds are provably wasted.
    """

    MAX_ROUNDS = 3            # 1 initial generation + up to 2 repair rounds
    FALLBACK_SQL = "SELECT 1"  # only used if no SQL was ever extracted

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL engine. Given a database schema and a "
        "natural-language question, produce exactly one SQLite query that "
        "answers the question. Use only tables and columns that appear in the "
        "schema. Reply with a single