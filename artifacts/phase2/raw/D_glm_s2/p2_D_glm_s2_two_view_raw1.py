"""Two independent SQL formulations (an explicit-JOIN view and a nested-subquery view) are written by the frozen solver, both are executed, and the first non-empty result set wins, with the JOIN view preferred when both return rows."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS2TwoView"]


class P2P2DGlmS2TwoView(SQLHarness):
    """Two-view (explicit JOIN vs. nested subquery) harness around a frozen solver.

    The mechanism lives in the control flow, not just the prompt:

    1. TWO independent calls to the frozen LLM, each pinned to a different
       formulation style (view A: explicit JOINs only; view B: nested
       subqueries only).
    2. BOTH candidates are executed against the database.
    3. Selection: the first candidate whose execution succeeded AND returned
       a non-empty result set is returned; if both are non-empty, the first
       (JOIN) view is returned; if neither returns rows, the first candidate
       that at least executed cleanly is returned as a fallback.
    """

    NAME = "P2P2DGlmS2TwoView"

    JOIN_SYSTEM = (
        "You are an expert SQLite text-to-SQL translator. You always combine "
        "tables with explicit JOIN clauses and you never write nested "
        "subqueries."
    )

    SUBQUERY_SYSTEM = (
        "You are an expert SQLite text-to-SQL translator. You always combine "
        "tables with nested subqueries (IN, NOT IN, EXISTS, or scalar "
        "subqueries) and you never write explicit JOIN clauses."
    )

    # ------------------------------------------------------------------ #
    # Prompt construction: one distinct prompt per formulation view
    # ------------------------------------------------------------------ #
    def _prompt(self, question: str, view: str) -> str:
        if view == "join":
            combine_rule = (
                "- Combine tables ONLY with explicit JOIN clauses, e.g. "
                "`FROM t1 JOIN t2 ON t1.x = t2.y`.\n"
                "- Do NOT use any subquery: no `IN (SELECT ...)`, no "
                "`EXISTS (...)`, no scalar `(SELECT ...)`."
            )
        else:  # "subquery" view
            combine_rule = (
                "- Combine tables ONLY with nested subqueries: "
                "`IN (SELECT ...)`, `NOT IN (SELECT ...)`, "
                "`EXISTS (SELECT ...)`, or a scalar `(SELECT ...)`.\n"
                "- Do NOT use any explicit JOIN clause."
            )
        return (
            f"Database schema:\n"
            f"{self.schema}\n\n"
            f"Question:\n"
            f"{question}\n\n"
            f"Write exactly one SQLite query that answers the question.\n"
            f"{combine_rule}\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Output the query in a single