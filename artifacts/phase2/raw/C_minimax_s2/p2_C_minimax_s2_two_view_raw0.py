"""Wraps a frozen weak solver with a two-view harness that generates join-based and subquery-based SQL, executes both, and returns the first non-empty result."""
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Generate join-based formulation via the frozen weak solver.
        join_prompt = (
            "You are a SQL expert. Given the schema and the question below, "
            "write a single SQL query that uses explicit JOIN syntax (INNER JOIN, "
            "LEFT JOIN, etc.) to combine tables.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return ONLY the SQL query, no explanation."
        )
        join_response = self.llm(join_prompt, system="", temperature=0.0, n=1)
        join_sql = bridge.extract_sql(join_response)

        # Step 2: Generate subquery-based formulation via the frozen weak solver.
        subquery_prompt = (
            "You are a SQL expert. Given the schema and the question below, "
            "write a single SQL query that uses subqueries (WHERE ... IN (SELECT ...) "
            "or nested SELECT) to combine tables, instead of explicit JOINs.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return ONLY the SQL query, no explanation."
        )
        subquery_response = self.llm(subquery_prompt, system="", temperature=0.0, n=1)
        subquery_sql = bridge.extract_sql(subquery_response)

        # Fallback: if extraction produced nothing, retry once on the raw response.
        if not join_sql and join_response:
            join_sql = self._fallback_extract(join_response)
        if not subquery_sql and subquery_response:
            subquery_sql = self._fallback_extract(subquery_response)

        # Step 3: Execute both candidates independently.
        join_result = self._safe_execute(join_sql)
        subquery_result = self._safe_execute(subquery_sql)

        # Step 4: Selection rule — prefer the formulation with non-empty rows;
        # if both are non-empty, return the first (join-based) one.
        if join_result["ok"] and join_result["rows"]:
            return join_sql
        if subquery_result["ok"] and subquery_result["rows"]:
            return subquery_sql
        if join_sql:
            return join_sql
        if subquery_sql:
            return subquery_sql
        # Last resort: return the join response cleaned up, or empty string.
        return join_sql or subquery_sql or ""

    def _safe_execute(self, sql: str):
        if not sql or not sql.strip():
            return {"ok": False, "rows": [], "error": "empty sql"}
        try:
            return self.execute(sql)
        except Exception as e:  # harness must never propagate executor errors
            return {"ok": False, "rows": [], "error": str(e)}

    def _fallback_extract(self, text: str) -> str:
        # Strip code fences and grab the first plausible SQL-looking statement.
        if not text:
            return ""
        cleaned = re.sub(r"