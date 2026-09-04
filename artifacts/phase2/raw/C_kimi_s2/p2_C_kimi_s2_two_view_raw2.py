"""Generates SQL from two independent formulations (join-based and subquery-based), executes both, and returns the candidate whose execution is non-empty, preferring the first on ties."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2TwoView(SQLHarness):
    """Two-view Text-to-SQL harness around the frozen weak solver.

    The frozen solver (``self.llm``) is queried twice with two independent
    formulation prompts:

    * View A -- a JOIN-centric formulation of the question.
    * View B -- a subquery-centric formulation, generated independently
      (it never sees View A's prompt output or SQL).

    Both extracted SQL candidates are executed against the database.  The
    candidate whose execution returns a non-empty row set is returned; if
    both are non-empty the first view wins, and if both are empty or fail
    the first view is returned as a final fallback.
    """

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL engine. Given a database schema and "
        "a natural-language question, produce exactly one syntactically "
        "valid SQL query that correctly answers the question. Output the "
        "SQL query only, with no explanations or commentary."
    )

    FORMULATION_A = (
        "Formulation requirement (View A): express the query logic "
        "primarily with explicit JOINs between the relevant tables. Avoid "
        "subqueries, IN-nesting and CTEs whenever a plain join (possibly "
        "combined with aggregation and GROUP BY) suffices."
    )

    FORMULATION_B = (
        "Formulation requirement (View B): express the query logic "
        "primarily with nested subqueries -- e.g. WHERE ... IN (SELECT ...), "
        "WHERE EXISTS (SELECT ...), or scalar subqueries in the SELECT or "
        "WHERE clauses -- instead of explicit JOIN clauses wherever "
        "possible."
    )

    def _build_prompt(self, question: str, formulation: str) -> str:
        schema = getattr(self, "schema", "") or ""
        return (
            "Database schema:\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            f"{formulation}\n\n"
            "Write the SQL query now. Output only the SQL."
        )

    @staticmethod
    def _first_text(llm_output) -> str:
        """Normalise the frozen solver's output (str, or list when n > 1)."""
        if isinstance(llm_output, (list, tuple)):
            return str(llm_output[0]) if llm_output else ""
        return str(llm_output) if llm_output else ""

    def _generate_sql(self, question: str, formulation: str) -> str:
        """Query the frozen solver once and extract the SQL candidate."""
        prompt = self._build_prompt(question, formulation)
        raw = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        text = self._first_text(raw)
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""
        return (sql or "").strip()

    def _run(self, sql: str):
        """Execute a candidate; return its row list if ok and non-empty, else None."""
        if not sql:
            return None
        try:
            result = self.execute(sql)
        except Exception:
            return None
        if not isinstance(result, dict):
            return None
        if result.get("ok") and result.get("rows"):
            return result["rows"]
        return None

    def solve(self, question: str) -> str:
        # View A: join-based formulation.
        sql_a = self._generate_sql(question, self.FORMULATION_A)

        # View B: subquery-based formulation -- independent of View A.
        sql_b = self._generate_sql(question, self.FORMULATION_B)

        # Execute both candidates.
        rows_a = self._run(sql_a)
        rows_b = self._run(sql_b)

        # Return the non-empty result; if both are non-empty, return the
        # first; if both are empty/failed, fall back to the first.
        if rows_a:
            return sql_a
        if rows_b:
            return sql_b
        return sql_a or sql_b