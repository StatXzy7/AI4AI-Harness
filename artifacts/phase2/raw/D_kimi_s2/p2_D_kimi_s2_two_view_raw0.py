"""Two-view Text-to-SQL harness: independently draft a join-based and a subquery-based SQL query, execute both, and return the first one whose result set is non-empty (preferring the join-based formulation on ties)."""

from ..harness_base import SQLHarness
from .. import bridge


_JOIN_SYSTEM = (
    "You are an expert SQLite query writer. Translate the user's "
    "natural-language question into one correct SQL query. Whenever the "
    "question involves more than one table, express the logic with explicit "
    "JOIN ... ON clauses (avoid nested subqueries). Output only the SQL "
    "query, optionally inside a