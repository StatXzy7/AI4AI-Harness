"""Sample multiple SQL candidates (one greedy plus temperature samples), execute each distinct read-only candidate to verify it actually runs, and return the executable candidate with the strongest support by voting on SQL text and on result signatures."""
# MECHANISM: vote

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G5(SQLHarness):
    """Self-consistency voting harness.

    Control flow per question (a real change over a single greedy call):

      1. GENERATE: one greedy completion (temperature 0) plus N-1 sampled
         completions (temperature 0.7) of the same prompt.
      2. TALLY: every completion is converted to SQL via bridge.extract_sql,
         cleaned, and deduplicated under a case/whitespace-insensitive key;
         each distinct candidate carries a vote count and remembers whether
         it came from the greedy call.
      3. VALIDATE: each distinct candidate is executed once against the
         database -- but only if it heuristically looks read-only, so the
         validation step can never mutate the database state -- and the rows
         it returns are condensed into a result signature.
      4. VOTE: among executable candidates, votes are pooled by identical
         result signature (so semantically equivalent queries reinforce each
         other), and the winning group's most popular query is returned. If
         nothing executes, the most frequent raw candidate wins; the greedy
         candidate breaks ties everywhere.
    """

    NAME = "p2p2b_glm_s2_g5"
    N_SAMPLES = 5
    SAMPLE_TEMPERATURE = 0.7
    SIG_ROW_LIMIT = 64

    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. Given a database schema and a "
        "question, write exactly one SQL query that answers the question. "
        "Use only the tables and columns present in the schema. Output only "
        "a single