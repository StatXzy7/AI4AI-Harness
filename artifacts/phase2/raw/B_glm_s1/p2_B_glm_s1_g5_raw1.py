"""Repair-loop Text-to-SQL harness: greedy SQL generation whose execution errors are fed back to the model to drive corrected regeneration until a query runs or the attempt budget is spent."""
# MECHANISM: repair

from typing import Dict, List

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G5(SQLHarness):
    """Greedy generation plus an execution-error repair loop.

    Control flow:
      1. Ask the model for one SQLite query (temperature 0.0).
      2. Execute that query against the live database via ``self.execute``.
      3. If execution fails, re-prompt the model with the failed query and its
         exact error message and ask for a corrected query; repeat up to
         ``MAX_ATTEMPTS`` total generations.
      4. Return the first query that executes successfully; if nothing ever
         executes, return the most recent non-empty generated query.
    """

    MAX_ATTEMPTS = 4
    BASE_TEMPERATURE = 0.0
    MAX_TEMPERATURE = 0.7

    SYSTEM_PROMPT = (
        "You are an expert SQLite analyst. Given a database schema and a natural "
        "language question, write exactly one SQLite SELECT query that answers the "
        "question. Use only tables and columns that appear in the schema. Respond "
        "with a single