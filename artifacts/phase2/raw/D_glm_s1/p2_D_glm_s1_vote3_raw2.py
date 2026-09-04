"""Self-consistency harness: draws three independent SQL attempts (n=3, temperature=0.7) from the frozen GLM solver, executes every attempt that parses, and returns the attempt whose result set wins a majority vote."""

import json

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS1Vote3"]


class P2P2DGlmS1Vote3(SQLHarness):
    """Voting wrapper around the frozen GLM text-to-SQL solver.

    The strategy lives in the control flow, not just the prompt:
      1. ONE llm call with n=3, temperature=0.7 -> three independent attempts.
      2. bridge.extract_sql each completion; keep every attempt that parses.
      3. self.execute every parsed attempt against the database.
      4. Bucket successful executions by canonical result; the bucket with
         the most votes wins (ties broken by earliest attempt); return the
         SQL that produced the winning result.
    Failed executions earn no vote; if nothing executes cleanly, the first
    parseable attempt is returned as a best-effort answer.
    """

    N_ATTEMPTS = 3
    SAMPLE_TEMPERATURE = 0.7

    SYSTEM_PROMPT = (
        "You are a careful SQLite expert. Given a database schema and a "
        "natural-language question, write exactly one SQLite query that "
        "answers the question. Output the query in a single