"""Repair-loop harness: greedily draft SQL, execute it against the database, and feed the execution error back to the model for up to three corrective regeneration rounds."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G4(SQLHarness):
    """Draft -> execute -> repair harness wrapping the frozen weak solver.

    Control flow (a real change over a single greedy call):

    1. Draft: one greedy LLM call turns (schema, question) into a candidate query.
    2. Execute: the candidate is run against the live database via self.execute.
    3. Repair: if execution fails, the exact DB error plus all previous failed
       attempts are appended to the prompt and the model must produce a
       *different* corrected query. Repeat up to MAX_ATTEMPTS.
    4. Fixed-point escape: if the model repeats a previously failed query, the
       repair round is sampled with a small temperature to break the loop.
    5. Return: the first query that executes cleanly, else the last attempt.
    """

    MAX_ATTEMPTS = 3

    SYSTEM = (
        "You are an expert text-to-SQL translator. Given a database schema and a "
        "natural-language question, output exactly one SQLite query that answers "
        "the question. Put the query in a single