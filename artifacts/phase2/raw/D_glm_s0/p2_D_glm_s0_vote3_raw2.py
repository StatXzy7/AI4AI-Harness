"""Draws 3 independent SQL candidates from the frozen solver (one llm call, temperature=0.7, n=3), executes every candidate that parses, and returns the candidate whose execution result wins the majority vote."""

from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS0Vote3(SQLHarness):
    """Self-consistency voting harness around a frozen weak Text-to-SQL solver.

    The strategy lives in the control flow, not only in the prompt:
      1. SAMPLE   - a single llm call with n=3 and temperature=0.7 produces
                    three independent completions (topped up with extra
                    single-shot calls if the bridge returns fewer than 3).
      2. PARSE    - each completion goes through bridge.extract_sql();
                    completions that yield no SQL are dropped.
      3. EXECUTE  - every parsed candidate is executed against the database
                    (memoized per unique SQL string).
      4. VOTE     - attempts are grouped by execution result; the result with
                    the most attempts wins and its earliest SQL is returned.
                    Ties break toward the result seen earliest; queries that
                    errored cast no vote (they produced no result).
    """

    ATTEMPTS = 3
    TEMPERATURE = 0.7

    SYSTEM_PROMPT = (
        "You are an expert data analyst who writes precise SQLite queries. "
        "Reply with exactly one SQL query inside a