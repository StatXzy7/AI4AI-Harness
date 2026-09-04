"""Two-phase text-to-SQL harness: an LLM generates SQLite SQL, the harness executes it, and on failure the exact SQLite error is fed back to the LLM to regenerate the query up to two times."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS2Repair"]


class P2P2DGlmS2Repair(SQLHarness):
    """Generate -> execute -> on failure, show the exact SQLite error and regenerate (max 2 repairs)."""

    # Number of regeneration rounds allowed AFTER the initial generation.
    MAX_REPAIRS: int = 2

    SYSTEM = (
        "You are an expert SQLite programmer translating natural-language questions "
        "into SQL. Respond with exactly one executable SQLite SQL statement inside a "
        "