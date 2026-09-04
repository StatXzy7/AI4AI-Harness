"""Generates SQLite SQL for a question and repairs it up to two times using execution error feedback."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2DDeepseekS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        last_sql = ""
        previous_sql = None
        previous_error = None

        for attempt in range(3):
            if attempt == 0:
                prompt = (
                    f"Given the following SQLite database schema:\n\n{schema}\n\n"
                    f"Write a SQLite SQL query to answer the question:\n\n{question}\n\n"
                    "Return only the SQL query without explanation."
                )
            else:
                prompt = (
                    f"Given the following SQLite database schema:\n\n{schema}\n\n"
                    f"Question:\n{question}\n\n"
                    f"The previous SQL query:\n{previous_sql}\n\n"
                    f"executed with the following SQLite error:\n{previous_error}\n\n"
                    "Please fix the SQL query to answer the question. "
                    "Return only the corrected SQL query without explanation."
                )

            response = self.llm(prompt, system="", temperature=0.0, n=1)
            if isinstance(response, list):
                response = response[0] if response else ""

            sql = bridge.extract_sql(response or "")
            last_sql = sql

            if not sql:
                previous_sql = sql
                previous_error = "No SQL query found in model response."
                continue

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            previous_sql = sql
            previous_error = result.get("error", "Unknown execution error")

        return last_sql