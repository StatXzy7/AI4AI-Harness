"""Draw multiple SQL candidates (a greedy anchor plus temperature samples), execute each, and majority-vote on their normalized result sets."""
# MECHANISM: vote

from collections import Counter, defaultdict

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS0G0(SQLHarness):
    """Self-consistency voting harness over the frozen Text-to-SQL solver.

    Control flow (a real change over a single greedy call):

      1. DRAW: ask the frozen solver K times for the same question -- once
         greedily (temperature 0.0, as an anchor) and K-1 times at a raised
         temperature so the samples genuinely differ.
      2. EXECUTE: run every candidate SQL against the database.
      3. VOTE (on answers): candidates that execute successfully are grouped
         by their normalized result multiset; the largest group is the
         majority *answer*.
      4. SELECT: within the winning answer group, return the most frequently
         proposed SQL text (ties -> earliest sample). If nothing executes,
         fall back to a plain majority vote over canonicalized SQL text.
    """

    K_SAMPLES = 5
    SAMPLE_TEMPERATURE = 0.8
    SIGNATURE_ROW_CAP = 200

    SYSTEM_PROMPT = (
        "You are an expert SQLite analyst. Given a database schema and a "
        "question, write exactly one SQL query that answers it. Output only "
        "the SQL inside a