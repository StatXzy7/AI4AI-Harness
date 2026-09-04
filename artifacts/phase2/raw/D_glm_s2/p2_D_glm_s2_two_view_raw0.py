"""Solves each question by drafting two independent SQL formulations -- a JOIN-based view and a subquery-based view -- executing both against the database, and returning the formulation whose execution yields rows, preferring the first view when both (or neither) return rows."""

from typing import Any, Dict, Optional

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS2TwoView"]


class P2P2DGlmS2TwoView(SQLHarness):
    """Two-view harness: JOIN formulation vs. subquery formulation, both
    executed; a non-empty result wins and ties go to the first view."""

    NAME = "P2P2DGlmS2TwoView"

    # Shared persona for both formulation calls.
    _SYSTEM = (
        "You are an expert SQLite programmer. Given a database schema and a "
        "natural-language question you write exactly one correct, executable "
        "SQLite SELECT statement, using only tables and columns that appear "
        "in the schema."
    )

    # View A: every cross-table access goes through explicit JOINs.
    _JOIN_VIEW = (
        "VIEW A - JOIN FORMULATION. Solve the task with explicit JOIN "
        "clauses (INNER JOIN / LEFT JOIN ... ON ...) whenever information "
        "from more than one table is needed. Subqueries are forbidden: "
        "express every cross-table condition through joins and, when "
        "aggregation is needed, use GROUP BY over the joined tables. "
        "Style example (illustrating the formulation only, unrelated to the "
        "schema): 'names of students who got an A in some course' -> "
        "SELECT s.name FROM students AS s INNER JOIN enrollments AS e "
        "ON e.student_id = s.id WHERE e.grade = 'A'"
    )

    # View B: every cross-table access goes through nested subqueries.
    _SUBQUERY_VIEW = (
        "VIEW B - SUBQUERY FORMULATION. Solve the task with nested "
        "subqueries instead of joins: reach other tables through "
        "IN (SELECT ...), NOT IN (SELECT ...), EXISTS (SELECT ...) or "
        "scalar subqueries in WHERE / HAVING. The JOIN keyword is "
        "forbidden; keep the outer query a single SELECT over one table "
        "and decompose the task into nested subqueries. Style example "
        "(illustrating the formulation only, unrelated to the schema): "
        "'names of students who got an A in some course' -> "
        "SELECT name FROM students WHERE id IN "
        "(SELECT student_id FROM enrollments WHERE grade = 'A')"
    )

    _OUTPUT_RULES = (
        "Reply with exactly one SQLite SELECT statement and nothing else, "
        "wrapped in a