"""Repair-loop harness: the frozen solver's SQL is executed against the database, and any execution error is fed back into a corrective regeneration pass until a query runs cleanly."""
# MECHANISM: repair

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G7(SQLHarness):
    """Execute-and-repair wrapper around the frozen weak solver.

    Control flow (a real change from a single greedy generation call):

    1. One greedy call asks the solver for a SQL query.
    2. The candidate query is executed against the database.
    3. If it executes cleanly, it is returned immediately.
    4. If it errors, the offending query plus the exact database error are
       folded into a repair prompt and the solver regenerates a corrected
       query; steps 2-4 repeat up to ``MAX_ATTEMPTS`` times in total.
    5. The loop stops early if the solver repeats a query that already
       failed (identical retries are futile) or if the statement is not a
       read-only query (returned unverified instead of being executed).
       If nothing ever executes cleanly, the most recent non-empty
       candidate is returned.
    """

    MAX_ATTEMPTS = 3

    _SYSTEM = (
        "You are an expert SQLite assistant. Given a database schema and a "
        "natural-language question, write exactly one SQL query that answers "
        "the question."
    )

    _QUERY_KEYWORDS = ("select", "with", "values", "explain")

    # ------------------------------------------------------------------ #
    # entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        attempts = self._max_attempts()

        candidates = []
        seen = set()
        last_sql = ""
        last_error = ""

        for attempt in range(1, attempts + 1):
            if attempt == 1:
                prompt = self._initial_prompt(question)
            else:
                prompt = self._repair_prompt(question, last_sql, last_error, attempt)

            sql = self._extract(self._complete(prompt))

            if not sql:
                # A useless reply becomes the repair target for the next pass.
                last_error = (
                    "No SQL statement could be extracted from the previous "
                    "reply. Respond with a single