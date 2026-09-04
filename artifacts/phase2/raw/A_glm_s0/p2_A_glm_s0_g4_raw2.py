"""Repair-loop harness: generate SQL greedily, execute it to verify, and feed the database's error messages back into the frozen solver for corrective regeneration."""

# MECHANISM: repair

from typing import Any, List, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS0G4(SQLHarness):
    """A single greedy text-to-SQL call hardened with an execute-verify-repair loop.

    Control flow (a real change vs. one greedy generation):

    1. Ask the frozen solver for one query (temperature 0, one sample).
    2. Statically validate the query (read-only, exactly one statement) and
       execute it against the real database via ``self.execute``.
    3. If the database rejects it, re-prompt the frozen solver with the
       rejected query *and the exact error string*, then execute the fix.
    4. Repeat for at most ``MAX_ATTEMPTS`` rounds.

    The first query that executes cleanly is returned immediately. If every
    round fails, the most recent error-informed query is returned as a best
    effort; destructive statements are never executed or returned.
    """

    MAX_ATTEMPTS = 4
    READONLY_PREFIXES = ("SELECT", "WITH")
    FALLBACK_SQL = "SELECT 1"

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL translator working against SQLite. "
        "Reply with exactly one SQL query and no extra prose. "
        "Put the query in a single