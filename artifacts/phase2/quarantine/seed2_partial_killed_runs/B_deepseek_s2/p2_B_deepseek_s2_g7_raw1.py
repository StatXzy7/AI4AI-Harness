"""Generates SQL, executes it, and uses execution errors to repair the SQL up to a fixed number of attempts."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G7(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        def generate_sql(prompt: str, temperature: float = 0.0) -> str:
            return bridge.extract_sql(self.llm(prompt, temperature=temperature))

        initial_prompt = (
            "You are an expert SQLite engineer. Given the following schema:\n"
            f"{schema}\n\n"
            f"Write a single SQLite query that answers the question: {question}\n"
            "Return only the SQL query, no explanation."
        )

        sql = generate_sql(initial_prompt)

        if not sql:
            # One fallback attempt with more direct formatting.
            fallback_prompt = (
                "Convert the following question into a SQLite query.\n"
                f"Schema:\n{schema}\n\nQuestion: {question}\n"
                "SQL:"
            )
            sql = generate_sql(fallback_prompt, temperature=0.2)

        if not sql:
            return ""

        max_attempts = 3
        for _ in range(max_attempts):
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "error": str(exc), "rows": []}

            if result.get("ok"):
                return sql

            error = result.get("error") or "Unknown execution error"

            repair_prompt = (
                "You are an expert SQLite engineer. The following SQL query was generated "
                f"for the question:\n{question}\n\n"
                f"Database schema:\n{schema}\n\n"
                f"The query:\n{sql}\n\n"
                f"It failed with this execution error:\n{error}\n\n"
                "Write a corrected SQLite query. Return only the SQL query, no explanation."
            )

            repaired_sql = generate_sql(repair_prompt)

            if not repaired_sql:
                # Repair did not produce usable SQL; stop and return the last attempt.
                break

            sql = repaired_sql

        return sql