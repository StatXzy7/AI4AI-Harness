"""Wrap a frozen weak solver by writing SQL for a question from two independent views -- a join-based formulation and a subquery-based formulation -- executing both, and returning the formulation whose result set is non-empty, preferring the join-based view when both are non-empty."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS2TwoView"]


class P2P2DGlmS2TwoView(SQLHarness):
    """Two-view harness: the question is formulated twice independently
    (join-based vs. subquery-based), both SQL candidates are executed, and
    the first one with a non-empty result wins; ties and empty/failed runs
    fall back to the first (join-based) formulation."""

    #: System prompt for the first, join-based formulation.
    JOIN_VIEW_SYSTEM = (
        "You are an expert Text-to-SQL engine for SQLite. "
        "Translate the question into exactly one SELECT statement. "
        "Combine tables exclusively with explicit JOIN clauses "
        "(INNER JOIN / LEFT JOIN ... ON). "
        "Do NOT use IN (SELECT ...), EXISTS, or any nested subquery. "
        "Output only the final SQL in a