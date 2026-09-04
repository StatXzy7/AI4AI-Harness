"""Execution-error repair: the harness generates SQLite greedily, executes it against the database, and feeds the exact error message back to the LLM for up to three corrective regenerations, returning the first query that executes cleanly."""
# MECHANISM: repair

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G4(SQLHarness):
    """Greedy generation plus an execution-error-driven repair loop.

    Control flow (a real change over a single greedy call):
      1. one greedy SQL generation from the schema + question;
      2. execute the candidate with self.execute;
      3. on failure, re-prompt the LLM with the failing SQL and the exact
         database error (plus every earlier failure) to obtain a fix;
      4. repeat up to MAX_REPAIRS times, escalating the sampling temperature
         if the model repeats a query that already failed;
      5. return the first query that executes cleanly, otherwise the most
         recent candidate (the one produced with the most feedback).
    """

    MAX_REPAIRS = 3
    ESCALATION_TEMPERATURE = 0.6
    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. You output exactly one SQL "
        "query and nothing else."
    )
    # A candidate is only executed if it is a read-only SELECT / WITH...SELECT.
    READ_ONLY_RE = re.compile(
        r"^\s*(?:/\*.*?\*/\s*|--[^\