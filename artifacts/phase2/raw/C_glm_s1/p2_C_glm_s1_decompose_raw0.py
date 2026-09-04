"""Decomposes the question into an ordered plan of sub-questions, answers each sub-question with its own small LLM call to obtain SQL fragments, then assembles the fragments into one final SQL statement that is executed and repaired on failure."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS1Decompose(SQLHarness):
    """Weak-solver harness implementing an explicit decomposition pipeline.

    Control flow (the strategy lives here, not only in the prompts):

        1. PLAN      - one LLM call splits the question into an ordered list of
                       sub-questions (parsed from a numbered list; falls back to
                       the whole question if planning fails).
        2. SOLVE     - one small, focused LLM call per sub-question produces a
                       SQL fragment; each call is made in order and sees the
                       fragments already produced, so later sub-questions can
                       depend on earlier ones.
        3. ASSEMBLE  - one LLM call merges the ordered fragments into a single
                       final SQL SELECT statement.
        4. VALIDATE  - the final SQL is executed against the database; on
                       failure, bounded repair calls retry with the database
                       error, with an independent direct-solve last resort.
    """

    NAME = "P2P2CGlmS1Decompose"

    MAX_SUBQUESTIONS = 5
    MAX_REPAIR_ATTEMPTS = 2

    DECOMP_SYSTEM = (
        "You are a Text-to-SQL planning assistant. Split the user's question "
        "into the shortest ordered list of sub-questions (1 to 5) that, when "
        "answered in sequence, yield the answer to the original question. "
        "Later sub-questions may depend on earlier ones. If the question is "
        "already atomic, output exactly one sub-question. Output ONLY a "
        "numbered list, one sub-question per line, and nothing else."
    )

    SUBQ_SYSTEM = (
        "You are a Text-to-SQL engine. Given a schema, the original question "
        "and a single focused sub-question, output one SQL SELECT statement "
        "(a self-contained fragment usable as a CTE or subquery) that answers "
        "only that sub-question. Output only the SQL, no explanation."
    )

    ASSEMBLE_SYSTEM = (
        "You are an expert Text-to-SQL engine. You are given an original "
        "question plus SQL fragments that answer its ordered sub-questions. "
        "Combine them (for example with CTEs or nested subqueries) into ONE "
        "final SQL SELECT statement that answers the original question. "
        "Output only the final SQL, no explanation."
    )

    REPAIR_SYSTEM = (
        "You are an expert Text-to-SQL engine. The candidate SQL failed "
        "against the database. Rewrite it into one valid SQL SELECT statement "
        "that answers the original question. Output only the corrected SQL, "
        "no explanation."
    )

    DIRECT_SYSTEM = (
        "You are an expert Text-to-SQL engine. Given a database schema and a "
        "question, output only one valid SQL SELECT statement that answers "
        "it, no explanation."
    )

    # ------------------------------------------------------------------
    # low-level helpers
    # ------------------------------------------------------------------

    def _llm(self, prompt, system=""):
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if not isinstance(out, str):
            out = str(out)
        return out.strip()

    def _run(self, sql):
        try:
            res = self.execute(sql)
        except Exception as exc:  # defensive: treat exceptions as failures
            return {"ok": False, "rows": [], "error": "exception: %s" % exc}
        if not isinstance(res, dict):
            return {"ok": False, "rows": [], "error": "unexpected execute() result"}
        return res

    def _sql_of(self, text):
        """Extract and sanitize a SQL statement from raw LLM output."""
        if not text:
            return ""
        sql = bridge.extract_sql(text) or ""
        if not sql:
            sql = text.strip()
        # backup fence stripping in case extraction left them
        sql = re.sub(r"^