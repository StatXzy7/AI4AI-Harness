"""Execution-guided voting: draw multiple SQL samples across a temperature ladder, execute every distinct read-only candidate, and return the query backed by the heaviest agreeing result set."""

# MECHANISM: vote

import re
from collections import OrderedDict

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G5(SQLHarness):
    """Multi-sample, execution-aware voting harness.

    Instead of trusting a single greedy generation, the control flow is:

    1. Sample ``TEMPERATURES`` completions (a greedy anchor plus a
       temperature ladder), so the weak solver proposes several distinct
       SQL candidates for the same question.
    2. Extract and whitespace-normalize one query per completion;
       identical queries accumulate vote weight (the greedy anchor counts
       double, since it sits at the model's mode).
    3. Execute each *distinct* candidate once, but only if it is read-only
       (``SELECT`` / ``WITH``); destructive statements are never run.
    4. Bucket successful candidates by an execution signature (row count
       plus the stringified cells of the leading rows), so queries that
       *compute the same answer* vote together even when their SQL text
       differs.
    5. Elect the candidate from the heaviest signature bucket; inside a
       bucket, ties go to the candidate with the highest individual
       weight, then lexicographic order. If nothing executes at all,
       fall back to a plain syntactic majority vote over the samples.
    """

    TEMPERATURES = (0.0, 0.6, 0.7, 0.8, 1.0)
    ANCHOR_WEIGHT = 2.0
    MAX_SIGNATURE_ROWS = 100

    SYSTEM_PROMPT = (
        "You are an expert SQLite analyst. Respond with exactly one SQL "
        "query inside a