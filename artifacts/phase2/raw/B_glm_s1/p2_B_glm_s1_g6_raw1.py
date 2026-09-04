"""Execution-guided self-repair: the greedily generated SQL is executed against the database, and any execution error is fed back to the model for up to three corrective regeneration rounds."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G6(SQLHarness):
    """Greedy Text-to-SQL generation wrapped in an execution-verified repair loop.

    Control flow (a real change versus a single greedy call):

        greedy LLM call --> execute SQL --ok--> return SQL
                                 |
                                error
                                 v
        repair prompt (schema + question + every query tried so far + the
        exact database error) --> greedy LLM call --> execute SQL --> ... loop

    The loop performs at most ``MAX_REPAIR_ROUNDS`` repair rounds, stops early
    if the model repeats a query that already failed, and returns the first
    candidate that executes successfully.  If every attempt fails, the most
    recent (most informed) non-empty candidate is returned as a fallback.
    """

    #: how many corrective regeneration rounds are allowed after the first try
    MAX_REPAIR_ROUNDS = 3
    #: truncate database error messages fed back to the model to this length
    MAX_ERROR_CHARS = 400

    SYSTEM_PROMPT = (
        "You are a careful SQLite expert. Reply with exactly one SQL query "
        "inside a