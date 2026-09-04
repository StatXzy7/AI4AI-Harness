"""Two-stage Text-to-SQL: draft SQL via LLM, then refine using schema-aware critic feedback."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge
import json
import re


class P2P2AMinimaxS1G4(SQLHarness):
    """
    Improvement: two-stage pipeline.
    Stage 1: draft SQL via LLM with execution-feedback repair loop (up to 2 repairs).
    Stage 2: a critic LLM pass that re-reads the question and the (possibly repaired)
    candidate SQL, and either returns it unchanged or rewrites it for clearer alignment
    with schema/columns. The final SQL is returned (we do NOT re-execute after stage 2
    to avoid inflating runtime; stage 2 is purely a reasoning-quality refinement).
    """

    # Hard caps to keep this safe under timeouts
    MAX_REPAIR_ATTEMPTS = 2

    def solve(self, question: str) -> str:
        # ---------- Stage 1: draft + repair-by-execution ----------
        # Initial generation prompt.
        draft_prompt = (
            "You are a Text-to-SQL generator.\n"
            "Given the schema and the question, produce ONE syntactically valid SQLite SQL "
            "query that answers the question. Output ONLY the SQL inside a