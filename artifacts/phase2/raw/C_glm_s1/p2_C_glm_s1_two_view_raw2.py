"""This harness generates two structurally independent SQL formulations of the same question (a JOIN-based view and a subquery-based view), executes both, and returns the formulation whose result set is non-empty, preferring the first view when both are non-empty."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS1TwoView(SQLHarness):
    """Two-view (JOIN-style vs. subquery-style) text-to-SQL harness that picks
    the candidate whose execution actually returns rows."""

    # -- View 1: flat, JOIN-based formulation --------------------------------
    JOIN_VIEW_SYSTEM = (
        "You are an expert SQLite programmer. Translate the user's question "
        "into exactly one SQLite SELECT statement.\n"
        "MANDATORY STYLE: combine tables using explicit JOIN clauses "
        "(INNER JOIN / LEFT JOIN ... ON). Do NOT use subqueries of any kind "
        "(no IN (SELECT ...), no EXISTS, no scalar subqueries) and do NOT use "
        "WITH / CTE blocks.\n"
        "Reply with only the SQL inside a