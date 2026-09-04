"""Draws three independent SQL attempts from the frozen solver in a single sampled call (temperature 0.7, n=3), executes every attempt that parses, and returns the SQL whose result set wins a majority vote."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS0Vote3"]


class P2P2DGlmS0Vote3(SQLHarness):
    """Three-way self-consistency voting over sampled SQL candidates.

    Mechanism (mirrored by the control flow in ``solve``):

    1. **Sample**   -- one ``self.llm`` call with ``n=3`` and
       ``temperature=0.7`` yields three *independent* completions of the
       same prompt.  The prompt itself asks for exactly one query, so each
       sampled completion is one attempt; the independence comes from the
       sampling parameters, not from the wording.
    2. **Parse**    -- every attempt is run through ``bridge.extract_sql``;
       attempts that yield no SQL are dropped.
    3. **Execute**  -- every attempt that parses is executed against the
       database.  Each successful execution casts exactly one vote keyed
       on its result set (row order ignored); a failed execution produces
       no result and therefore casts no vote.
    4. **Vote**     -- the result set with the most votes wins (ties go to
       the result seen first) and the earliest SQL that produced it is
       returned.
    5. **Fallbacks** -- if nothing parses, the first raw sample is
       returned; if everything parses but nothing runs, the first
       candidate is returned.
    """

    N_ATTEMPTS = 3
    TEMPERATURE = 0.7

    SYSTEM_PROMPT = (
        "You are a precise text-to-SQL engine. Given a database schema and "
        "a natural-language question, output exactly one SQL query that "
        "answers the question, and nothing else."
    )

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #

    def _prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            "----------------\n"
            f"{self.schema}\n"
            "----------------\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question using only the "
            "tables and columns shown in the schema.\n"
            "Respond with a single