"""Two-view weak solver: writes each question as an independent join-based and an independent subquery-based SQL query, executes both, and returns the first one that produces rows."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CGlmS1TwoView"]


class P2P2CGlmS1TwoView(SQLHarness):
    """Solves each question via two independent formulations (join-based and subquery-based), executes both, and returns the first non-empty result, preferring the join view on ties."""

    NAME = "P2P2CGlmS1TwoView"

    JOIN_SYSTEM = (
        "You are an expert SQLite developer. Answer the user's question with "
        "exactly one SQL SELECT statement written as a single flat query: "
        "combine tables with JOIN ... ON (or comma joins plus WHERE "
        "conditions) and use GROUP BY / HAVING for aggregation. NEVER use "
        "subqueries: no IN (SELECT ...), no EXISTS, and no nested SELECT in "
        "the FROM or WHERE clauses."
    )

    SUBQUERY_SYSTEM = (
        "You are an expert SQLite developer. Answer the user's question with "
        "exactly one SQL SELECT statement written in a nested style: the "
        "outer query reads from a single table, and every cross-table "
        "relationship is expressed with subqueries -- IN (SELECT ...), "
        "NOT IN, EXISTS, or scalar subqueries. NEVER use JOIN; compose the "
        "whole answer out of nested subqueries."
    )

    PROMPT_TEMPLATE = (
        "Database schema:\n"
        "{schema}\n\n"
        "Question: {question}\n\n"
        "Write the SQL query that answers this question. Reply with a single "
        "