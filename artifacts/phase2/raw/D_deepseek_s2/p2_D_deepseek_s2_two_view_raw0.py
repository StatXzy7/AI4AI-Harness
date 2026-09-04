"""Generates two SQL formulations (join-based and subquery-based) and returns the SQL whose execution yields non-empty rows, preferring the first if both succeed."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2TwoView(SQLHarness):
    """Harness that creates and compares two SQL formulations for a Text-to-SQL question."""

    def solve(self, question: str) -> str:
        """
        Generate two independent SQL formulations (join-based and subquery-based),
        execute both, and return the SQL whose result is non-empty. If both are
        non-empty, return the first. Fall back to the first successful execution
        if neither is non-empty.
        """
        sql_join = self._generate_sql(question, "join")
        sql_subquery = self._generate_sql(question, "subquery")

        result_join = self._safe_execute(sql_join)
        result_subquery = self._safe_execute(sql_subquery)

        join_nonempty = bool(result_join.get("ok")) and len(result_join.get("rows") or []) > 0
        subquery_nonempty = bool(result_subquery.get("ok")) and len(result_subquery.get("rows") or []) > 0

        if join_nonempty:
            return sql_join
        if subquery_nonempty:
            return sql_subquery

        # If neither is non-empty, prefer a successful execution.
        if result_join.get("ok"):
            return sql_join
        if result_subquery.get("ok"):
            return sql_subquery

        # Last resort: return the first formulation.
        return sql_join

    def _generate_sql(self, question: str, style: str) -> str:
        """Generate a SQL query using the specified style (join or subquery)."""
        if style == "join":
            instruction = (
                "Use explicit JOIN operations between tables. "
                "Avoid subqueries and CTEs."
            )
        else:
            instruction = (
                "Use subqueries (nested SELECT statements) instead of JOIN operations. "
                "Avoid explicit JOINs and CTEs."
            )

        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write a single SQL SELECT statement that answers the question. "
            f"{instruction} Return only the SQL query, no explanation."
        )
        system = "You are an expert SQL developer. Write only the SQL query."

        raw_response = self._call_llm(prompt, system)
        extracted_sql = bridge.extract_sql(raw_response)
        return extracted_sql if extracted_sql else raw_response.strip()

    def _call_llm(self, prompt: str, system: str = "") -> str:
        """Call the LLM and normalize the response to a string."""
        response = self.llm(prompt, system=system, temperature=0.0, n=1)

        if isinstance(response, (list, tuple)):
            return str(response[0]) if response else ""
        if isinstance(response, dict):
            choices = response.get("choices", [])
            if choices:
                first = choices[0]
                if isinstance(first, dict):
                    return str(first.get("text", ""))
                return str(first)
            return str(response.get("text", ""))
        return str(response)

    def _safe_execute(self, sql: str):
        """Execute SQL and always return a dict with ok, rows, and error keys."""
        try:
            result = self.execute(sql)
            if not isinstance(result, dict):
                return {"ok": False, "rows": [], "error": "execute did not return a dict"}
            return result
        except Exception as exc:  # noqa: BLE001 - deliberate broad catch for external calls
            return {"ok": False, "rows": [], "error": str(exc)}