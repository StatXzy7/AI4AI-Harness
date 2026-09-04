"""P2P2DGlmS0Vote3 draws 3 independent SQL candidates from the frozen solver (n=3, temperature=0.7), executes every candidate that parses, and returns the SQL whose result set wins the execution-based majority vote."""

from typing import Any, Dict, List, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS0Vote3"]


class P2P2DGlmS0Vote3(SQLHarness):
    """Self-consistency harness: sample 3 SQLs independently, execute all that parse, return the SQL behind the majority result."""

    ATTEMPTS = 3
    TEMPERATURE = 0.7
    FALLBACK_SQL = "SELECT 1"

    SYSTEM_PROMPT = (
        "You are an expert SQLite analyst. Given a database schema and a "
        "question, write exactly one SQLite SELECT query that answers the "
        "question. Output only the query in a single