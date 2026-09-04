"""Generates an initial SQL query, executes it, and uses SQLite error feedback to repair it up to two times."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS0Repair(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        previous_sql = ""
        previous_error = ""
        final_sql = ""

        for attempt in range(3):
            if attempt == 0:
                prompt = (
                    "You are a text-to-SQL assistant. Given the following SQLite database schema, "
                    "write a valid SQLite SELECT query that answers the question.\n\n"
                    f"Schema:\n{schema}\n\n"
                    f"Question:\n{question}\n\n"
                    "Return only the SQL query, without any explanation."
                )
            else:
                prompt = (
                    "The following SQL query failed with a SQLite error.\n\n"
                    f"Previous SQL:\n{previous_sql}\n\n"
                    f"SQLite error:\n{previous_error}\n\n"
                    "Using the schema below, fix the query so it runs successfully and answers the original question.\n\n"
                    f"Schema:\n{schema}\n\n"
                    f"Question:\n{question}\n\n"
                    "Return only the corrected SQL query, without any explanation."
                )

            raw_output = self.llm(prompt, system="", temperature=0.0, n=1)
            if isinstance(raw_output, list):
                raw_output = raw_output[0] if raw_output else ""
            raw_output = str(raw_output)

            sql = bridge.extract_sql(raw_output) or raw_output.strip()
            if not sql:
                previous_sql = raw_output.strip()
                previous_error = "Could not extract a SQL query from the model response."
                continue

            final_sql = sql

            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}

            if isinstance(result, dict) and result.get("ok"):
                return sql

            if isinstance(result, dict):
                previous_error = result.get("error", "Unknown error")
            else:
                previous_error = str(result)

            previous_sql = sql

        return final_sql