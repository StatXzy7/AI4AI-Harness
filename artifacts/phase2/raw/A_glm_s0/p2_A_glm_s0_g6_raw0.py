"""Execution-aware self-consistency voting: sample several SQL candidates (a greedy anchor plus temperature samples with light prompt nudges), deduplicate and tally them, execute each distinct candidate against the database, and return the strongest executable query."""
# MECHANISM: vote

import re
from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS0G6(SQLHarness):
    """Multi-sample voting harness around the frozen solver.

    Control flow -- a real change from a single greedy call:

    1. SAMPLE: draw len(SAMPLING_PLAN) candidates from the frozen LLM.
       The first draw is greedy (temperature 0) and anchors the pool; the
       remaining draws use temperature 0.8 with small prompt nudges so the
       pool is diverse rather than K copies of one answer.
    2. NORMALIZE + TALLY: extract one SQL statement per completion, strip
       code fences / statement terminators, and deduplicate on a
       whitespace-collapsed key while keeping vote counts and first-seen
       order.
    3. VALIDATE: execute each *distinct* candidate once against the
       database. Execution is used purely as a selection signal -- errors
       are never fed back for regeneration.
    4. SELECT: rank candidates by (read-only shape, executes OK, votes,
       returns rows, seen earlier) and return the winner. If nothing
       executes, the most-voted candidate is still returned.
    """

    SAMPLING_PLAN = (
        (0.0, ""),
        (0.8, "Be concise: avoid joins and columns the answer does not need."),
        (0.8, "Decide which table holds the answer before writing the query."),
        (0.8, "Check that COUNT/SUM/AVG/MAX/MIN, GROUP BY and ORDER BY match the question exactly."),
        (0.8, "Prefer explicit column names over SELECT *."),
    )

    SYSTEM = (
        "You are an expert SQLite programmer. Translate the user's question "
        "into one correct SQLite SELECT query. Use only tables and columns "
        "that appear in the given schema. Output the query inside a