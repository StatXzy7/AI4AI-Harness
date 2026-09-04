"""Execution-grounded self-consistency: the harness samples several candidate queries, executes each against the database, and returns the candidate whose result is backed by the largest cluster of agreeing sample executions."""
# MECHANISM: vote

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS0G1(SQLHarness):
    """Self-consistency voting where ballots are cast on execution results.

    Instead of trusting a single greedy decoding, the harness draws one greedy
    anchor plus several temperature samples, runs every distinct candidate
    against the real database, groups the executions by a normalized result
    signature (so superficially different but semantically equivalent queries
    pool their votes), and returns the query behind the strongest result
    cluster.
    """

    NUM_SAMPLES = 5            # total generations (1 greedy anchor + 4 samples)
    SAMPLE_TEMPERATURE = 0.8   # temperature for the non-greedy draws
    MAX_SIGNATURE_ROWS = 100   # rows considered when fingerprinting a result

    SYSTEM = (
        "You are an expert text-to-SQL engine. Given a database schema and a "
        "natural-language question, output exactly one SQLite query that "
        "answers the question. Output the query only, wrapped in a