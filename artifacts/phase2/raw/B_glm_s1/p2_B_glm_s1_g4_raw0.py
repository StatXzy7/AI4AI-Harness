"""Greedy text-to-SQL draft hardened by an execution-feedback repair loop that replays SQLite errors back to the frozen LLM for up to three corrected regenerations."""
# MECHANISM: repair
from typing import Any, Dict, List, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G4(SQLHarness):
    """Draft-then-repair harness around a frozen greedy text-to-SQL solver.

    Improvement over a single greedy call:

    1. Draft: one greedy (temperature 0) LLM call turns the question plus the
       schema into a candidate SELECT statement.
    2. Execute: the candidate is run against the database.
    3. Repair: if (and only if) execution fails, the exact SQLite error and the
       full history of failed attempts are fed back into a new LLM call that
       must produce a corrected statement. Candidates are deduplicated, so the
       loop either makes progress or stops early.
    4. Return: the first candidate that executes cleanly, otherwise the most
       recent repair.
    """

    MAX_REPAIR_ROUNDS = 3
    MAX_ERROR_CHARS = 600
    MAX_SQL_CHARS = 2000

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL engine. Given a database schema and a "
        "question, you output exactly one SQLite query that answers the "
        "question. The query must be a single read-only SELECT statement. "
        "Reply with only the SQL inside one