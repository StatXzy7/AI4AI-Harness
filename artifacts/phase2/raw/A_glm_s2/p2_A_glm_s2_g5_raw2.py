"""Greedy SQL generation wrapped in an execution-repair loop: every candidate query is executed against the database and, when execution fails, the exact error message is fed back to the frozen solver to drive a corrective regeneration (up to two repair rounds) before falling back to the last candidate."""
# MECHANISM: repair

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G5(SQLHarness):
    """One greedy generation, then up to two execution-error-driven repairs."""

    MAX_ATTEMPTS = 3            # 1 initial generation + up to 2 repair rounds
    REPAIR_TEMPERATURE = 0.3    # nudge off the greedy failure on repair rounds

    SYSTEM_PROMPT = (
        "You are a precise text-to-SQL translator. Given a database schema and "
        "a natural-language question you output exactly one SQLite query that "
        "answers the question. Reply with the SQL statement only: no prose, "
        "no markdown fences, no explanation."
    )

    _SQL_STARTERS = (
        "SELECT", "WITH", "VALUES", "PRAGMA", "INSERT",
        "UPDATE", "DELETE", "CREATE", "DROP", "ALTER",
    )
    _FENCE_RE = re.compile(r"