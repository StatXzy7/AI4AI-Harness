"""Self-repair harness that iteratively refines SQL using execution feedback."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G1(SQLHarness):
    """Text-to-SQL harness with execution-guided self-repair."""

    MAX_REPAIRS = 3

    def solve(self, question: str) -> str:
        schema = self.schema

        # Stage 1: initial generation
        sql = self._generate(question, schema, error_feedback="")
        if sql is None:
            return ""

        # Stage 2: iterative repair loop
        for attempt in range(self.MAX_REPAIRS):
            result = self.execute(sql)

            if result.get("ok"):
                # Verify the query actually returns rows
                rows = result.get("rows", [])
                if rows:
                    return sql
                # Empty result set - try to broaden the query
                error_feedback = (
                    "The query executed successfully but returned no rows. "
                    "Please broaden the search conditions, check for case sensitivity, "
                    "or consider alternative column/table names."
                )
            else:
                error_msg = result.get("error", "Unknown error")
                error_feedback = (
                    f"SQL execution failed with error: {error_msg}\n"
                    "Please fix the SQL syntax or schema references."
                )

            # Regenerate with feedback
            new_sql = self._generate(question, schema, error_feedback=error_feedback, prior_sql=sql)
            if new_sql is None:
                break

            # Avoid no-op: if the regenerated SQL is identical, stop
            if self._normalize_sql(new_sql) == self._normalize_sql(sql):
                break
            sql = new_sql

        return sql

    def _generate(self, question: str, schema: str, error_feedback: str = "", prior_sql: str = "") -> str:
        """Generate SQL, optionally conditioned on prior attempt and feedback."""
        system = (
            "You are an expert SQL generator. Given a database schema and a natural "
            "language question, produce a single valid SQL query that answers it. "
            "Return ONLY the SQL statement with no prose, no markdown fences."
        )

        if error_feedback and prior_sql:
            user = (
                f"Schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                f"Previous SQL attempt:\n{prior_sql}\n\n"
                f"Feedback: {error_feedback}\n\n"
                "Generate a corrected SQL query."
            )
        elif error_feedback:
            user = (
                f"Schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                f"Feedback: {error_feedback}\n\n"
                "Generate a SQL query that addresses the feedback."
            )
        else:
            user = (
                f"Schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                "Generate the SQL query."
            )

        raw = self.llm(user, system=system, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)
        return sql

    @staticmethod
    def _normalize_sql(sql: str) -> str:
        """Normalize SQL for equality comparison."""
        return " ".join(sql.lower().split())