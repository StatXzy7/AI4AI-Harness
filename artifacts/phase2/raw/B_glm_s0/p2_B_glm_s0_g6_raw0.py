"""Repair-loop text-to-SQL harness: the frozen solver's greedy SQL candidate is executed, and each execution error (together with the offending query) is fed back to the solver for up to three corrective regeneration rounds."""

# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS0G6(SQLHarness):
    """Greedy generation followed by execution-error-driven repair rounds."""

    #: total solver calls per question: 1 greedy generation + up to 3 repairs
    MAX_ATTEMPTS = 4

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL translator. Given a database schema and a "
        "natural-language question, write exactly one SQLite query that answers the "
        "question. Reply with a single SQL query inside a