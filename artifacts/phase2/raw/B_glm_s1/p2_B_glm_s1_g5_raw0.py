"""Execution-grounded self-consistency voting: several SQL candidates are sampled from the frozen solver, each is executed against the database, and the candidate whose result set wins the most agreement is returned."""
# MECHANISM: vote

import re
from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G5(SQLHarness):
    """Self-consistency voting over a frozen weak text-to-SQL solver.

    Instead of a single greedy generation, ``solve``:

      1. draws ``N_CANDIDATES`` SQL candidates -- one greedy seed at
         temperature 0.0 plus stochastic samples at ``TEMPERATURE``,
         alternating between two prompt variants so the sampled reasoning
         paths stay diverse;
      2. normalizes every reply with ``bridge.extract_sql`` and executes it
         (read-only statements only), summarising each successful run by a
         result signature ``(row count, repr of the first SIG_ROWS rows)``;
      3. clusters the executable candidates by that signature and elects the
         largest cluster, so two queries that return the same rows count as
         the same answer even when their SQL text differs;
      4. breaks ties toward a cluster containing the greedy seed, then toward
         the most frequent SQL text inside the cluster, then toward the
         earliest sample;
      5. falls back to a plain textual majority vote over the extracted SQL
         strings when no candidate executes successfully.

    Execution results are never fed back into generation (that would be
    repair); they are used only to *select* among the sampled candidates.
    """

    N_CANDIDATES = 5   # total candidate queries drawn per question
    TEMPERATURE = 0.7  # sampling temperature for the non-greedy draws
    SIG_ROWS = 64      # rows compared when signing a result set
    READ_ONLY = ("SELECT", "WITH", "VALUES")

    SYSTEM = (
        "You are an expert text-to-SQL writer. Use only tables and columns "
        "that appear in the schema. Output exactly one SQLite query inside a "
        "