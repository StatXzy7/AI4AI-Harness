"""Generate SQL from two independent formulations (join-based and subquery-based), execute both, and return the first whose result is non-empty (preferring the join-based one on ties)."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2TwoView(SQLHarness):
    """Two-view Text-to-SQL harness.

    The frozen weak solver is queried twice with independent formulation
    instructions: once for a JOIN-based query and once for a subquery-based
    query. Both candidate queries are executed against the database, and the
    harness returns the first candidate that yields a non-empty result set
    (the JOIN-based candidate wins ties and is the fallback when both are
    empty or fail).
    """

    JOIN_SYSTEM = (
        "You are an expert SQLite query writer. Formulate every answer as a "
        "single SQL query built around explicit JOIN clauses between tables. "
        "Avoid subqueries; express filtering and aggregation through JOIN, "
        "WHERE, GROUP BY, HAVING, and ORDER BY."
    )
    SUBQUERY_SYSTEM = (
        "You are an expert SQLite query writer. Formulate every answer as a "
        "single SQL query built around subqueries (nested SELECTs used with "
        "IN, EXISTS, NOT IN, or scalar comparisons). Avoid JOIN clauses; "
        "express relationships between tables through correlated or "
        "uncorrelated subqueries."
    )

    def _draft_sql(self, question: str, system: str, instruction: str) -> str:
        """Ask the frozen solver for one formulation and extract its SQL."""
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"{instruction}\n"
            "Respond with only the SQL query, enclosed in a