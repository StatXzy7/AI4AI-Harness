"""Solves each question by independently drafting two SQL formulations (a JOIN-based view and a subquery-based view), executing both against the database, and returning the first view whose result rows are non-empty."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS1TwoView(SQLHarness):
    """Two-view (join vs. subquery) draft-and-test harness over a frozen solver."""

    NAME = "p2p2c_glm_s1_two_view"

    # View A: force an explicit JOIN-based formulation.
    JOIN_VIEW_SYSTEM = (
        "You are an expert SQLite programmer. Answer with one single SQLite "
        "query. Formulate the solution using explicit JOIN clauses whenever "
        "facts from multiple tables must be combined; do not use nested or "
        "correlated subqueries."
    )

    # View B: force a nested-subquery formulation.
    SUBQUERY_VIEW_SYSTEM = (
        "You are an expert SQLite programmer. Answer with one single SQLite "
        "query. Formulate the solution using nested subqueries with IN, "
        "NOT IN, EXISTS, or scalar subqueries instead of JOIN clauses; do "
        "not write any JOIN."
    )

    PROMPT_TEMPLATE = (
        "Database schema:\n"
        "{schema}\n\n"
        "Question: {question}\n\n"
        "Reply with exactly one SQLite query in a