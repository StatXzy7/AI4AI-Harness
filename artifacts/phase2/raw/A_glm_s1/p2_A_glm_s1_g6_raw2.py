"""Repair-loop harness: generate SQL greedily, execute it, and feed each execution error back to the LLM for up to two corrective regenerations, returning the first query that executes cleanly or the last candidate as a fallback."""
# MECHANISM: repair

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G6(SQLHarness):
    """Text-to-SQL harness that repairs SQL using execution-error feedback."""

    # One initial greedy generation plus up to two error-driven repair rounds.
    MAX_ATTEMPTS = 3

    SYSTEM_PROMPT = (
        "You are an expert SQLite text-to-SQL engine. Given a database schema "
        "and a natural-language question, output a single read-only SQLite "
        "query that answers the question. Respond with exactly one SQL "
        "statement inside a