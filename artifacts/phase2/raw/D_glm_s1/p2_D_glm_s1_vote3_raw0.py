"""Majority-vote (self-consistency) harness: draws 3 independent SQL attempts from the frozen solver (n=3, temperature=0.7), executes every attempt that parses, and returns the SQL backed by the majority execution outcome."""

from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS1Vote3(SQLHarness):
    """Voting wrapper around the frozen text-to-SQL solver.

    The strategy lives in the control flow, not just in the prompt:

        1. SAMPLING  -- one call to the frozen solver with n=3 and
                        temperature=0.7 yields 3 independent SQL attempts.
        2. EXECUTION -- every attempt that parses (bridge.extract_sql returns
                        a non-empty query) is executed via self.execute; each
                        parsed attempt casts exactly one vote.
        3. VOTING    -- executions are bucketed by outcome (ok flag + row set
                        for successes, normalized error text for failures);
                        the SQL of the largest bucket wins, with ties broken
                        toward a successful outcome and then toward the
                        earliest attempt.

    API provided by SQLHarness: self.schema (str),
    self.llm(prompt, system="", temperature=0.0, n=1), and
    self.execute(sql) -> {"ok": bool, "rows": [...], "error": str}.
    """

    N_ATTEMPTS = 3
    SAMPLING_TEMPERATURE = 0.7

    SYSTEM_PROMPT = (
        "You are a precise text-to-SQL translator for SQLite. Given a database "
        "schema and a question, write exactly one SQL query that answers the "
        "question. Reply with a single query inside one