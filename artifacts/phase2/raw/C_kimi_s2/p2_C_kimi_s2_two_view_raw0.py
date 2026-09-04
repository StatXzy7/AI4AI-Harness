"""Harness that drafts the question as two independent SQL formulations (join-based and subquery-based), executes both, and returns the first one whose execution yields a non-empty result."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2TwoView(SQLHarness):
    """Two-view Text-to-SQL harness over a frozen weak solver.

    The solver is prompted twice for the same question under two
    independent formulation constraints:

    * View A -- join-based: explicit ``JOIN ... ON`` clauses between the
      relevant tables, no nested subqueries.
    * View B -- subquery-based: nested ``IN (SELECT ...)`` / ``EXISTS
      (SELECT ...)`` predicates over individual tables, no explicit joins.

    Both candidate SQL strings are extracted and executed. The first
    candidate whose execution succeeds and returns at least one row is
    returned; if neither produces rows, the first (join-based) candidate
    is returned as the fallback.
    """

    SYSTEM = (
        "You are an expert Text-to-SQL engine. Given a database schema and "
        "a natural-language question, write exactly one syntactically valid "
        "SQL query that answers the question. Output only the SQL query, "
        "with no explanation and no markdown."
    )

    JOIN_PROMPT = (
        "Database schema:\n"
        "{schema}\n\n"
        "Question: {question}\n\n"
        "Write ONE SQL query that answers the question.\n"
        "Formulation requirement (View A): express the logic primarily with "
        "explicit JOIN ... ON clauses between the relevant tables; do NOT "
        "use nested subqueries or IN (SELECT ...) predicates.\n"
        "Output only the SQL query."
    )

    SUBQUERY_PROMPT = (
        "Database schema:\n"
        "{schema}\n\n"
        "Question: {question}\n\n"
        "Write ONE SQL query that answers the question.\n"
        "Formulation requirement (View B): express the logic primarily with "
        "nested subqueries, i.e. WHERE ... IN (SELECT ...) or WHERE EXISTS "
        "(SELECT ...) predicates over individual tables; do NOT use "
        "explicit JOIN clauses.\n"
        "Output only the SQL query."
    )

    def solve(self, question: str) -> str:
        # 1. Two independent formulations of the same question.
        join_sql = self._draft(self.JOIN_PROMPT, question)
        subquery_sql = self._draft(self.SUBQUERY_PROMPT, question)

        # 2. Execute both candidates (no short-circuit: both are run).
        join_result = self._run(join_sql)
        subquery_result = self._run(subquery_sql)

        # 3. Return the first candidate with a non-empty result.
        if self._non_empty(join_result):
            return join_sql
        if self._non_empty(subquery_result):
            return subquery_sql
        # Both empty or failed: fall back to the first formulation.
        return join_sql or subquery_sql

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _draft(self, template: str, question: str) -> str:
        """Ask the frozen solver for one formulation and extract its SQL."""
        prompt = template.format(schema=self.schema, question=question)
        text = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""
        return bridge.extract_sql(text)

    def _run(self, sql: str) -> dict:
        """Execute a candidate query, treating empty SQL as a failure."""
        if not sql or not sql.strip():
            return {"ok": False, "rows": [], "error": "empty sql"}
        return self.execute(sql)

    @staticmethod
    def _non_empty(result: dict) -> bool:
        """A result counts only if it executed cleanly and returned rows."""
        return bool(result.get("ok")) and bool(result.get("rows"))