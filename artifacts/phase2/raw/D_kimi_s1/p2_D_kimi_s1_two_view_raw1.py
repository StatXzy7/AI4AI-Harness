"""Two-view Text-to-SQL harness: independently draft a join-based and a subquery-based SQL formulation, execute both, and return the first one whose result is non-empty (preferring the join-based view on ties or total failure)."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS1TwoView(SQLHarness):
    """Generates SQL from two independent formulations (join-based and
    subquery-based), executes both candidates, and selects the first candidate
    that returns a non-empty result set, falling back to the first candidate
    when both are empty or erroneous."""

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL system. Given a database schema and a "
        "natural-language question, produce exactly one syntactically valid "
        "SQLite SQL query. Output only the SQL, with no explanations."
    )

    JOIN_INSTRUCTION = (
        "Formulate the answer as a JOIN-BASED query: use explicit JOIN ... ON "
        "clauses to combine tables and plain WHERE conditions for filtering. "
        "Avoid subqueries unless they are strictly unavoidable."
    )

    SUBQUERY_INSTRUCTION = (
        "Formulate the answer as a SUBQUERY-BASED query: express table "
        "combination and filtering through nested SELECTs (IN, EXISTS, "
        "correlated subqueries, or derived tables in FROM) instead of "
        "explicit JOIN clauses wherever possible."
    )

    def _draft_sql(self, question: str, formulation_instruction: str) -> str:
        """Ask the frozen LLM for one SQL query under a given formulation."""
        prompt = (
            f"{formulation_instruction}\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL query:"
        )
        response = self.llm(
            prompt,
            system=self.SYSTEM_PROMPT,
            temperature=0.0,
            n=1,
        )
        return bridge.extract_sql(response)

    def _run(self, sql: str) -> dict:
        """Execute a candidate, converting any failure into a uniform result."""
        if not sql or not sql.strip():
            return {"ok": False, "rows": [], "error": "empty sql"}
        try:
            return self.execute(sql)
        except Exception as exc:  # defensive: treat crashes as failures
            return {"ok": False, "rows": [], "error": str(exc)}

    @staticmethod
    def _is_non_empty(result: dict) -> bool:
        """A view 'wins' only if it executed cleanly and returned rows."""
        return bool(result.get("ok")) and bool(result.get("rows"))

    def solve(self, question: str) -> str:
        # View 1: join-based formulation.
        join_sql = self._draft_sql(question, self.JOIN_INSTRUCTION)
        # View 2: independent subquery-based formulation.
        subquery_sql = self._draft_sql(question, self.SUBQUERY_INSTRUCTION)

        # Execute both candidates regardless of overlap between the views.
        join_result = self._run(join_sql)
        subquery_result = self._run(subquery_sql)

        # Selection rule: first non-empty result wins; ties go to view 1.
        if self._is_non_empty(join_result):
            return join_sql
        if self._is_non_empty(subquery_result):
            return subquery_sql
        # Neither view produced rows: fall back to the first formulation.
        return join_sql