"""Repair loop that executes generated SQL and asks the LLM to fix any execution errors."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS1G4(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        max_attempts = 3
        last_sql = ""
        last_error = ""

        for attempt in range(max_attempts):
            if attempt == 0:
                prompt = (
                    "You are an expert SQL engineer. Write a SQL query to answer the user's question.\n"
                    "Use only the tables and columns in the provided schema.\n"
                    "Return only the SQL query, with no explanation or markdown.\n\n"
                    f"Schema:\n{schema}\n\n"
                    f"Question:\n{question}\n\n"
                    "SQL:"
                )
            else:
                prompt = (
                    "You are an expert SQL engineer. A previous SQL query failed to execute.\n"
                    "Fix the query based on the execution error and return only the corrected SQL query,\n"
                    "with no explanation or markdown.\n\n"
                    f"Schema:\n{schema}\n\n"
                    f"Question:\n{question}\n\n"
                    f"Previous SQL:\n{last_sql}\n\n"
                    f"Execution error:\n{last_error}\n\n"
                    "Corrected SQL:"
                )

            raw = self.llm(prompt, system="", temperature=0.0, n=1)
            if isinstance(raw, list):
                raw = raw[0] if raw else ""
            raw = str(raw)

            sql = bridge.extract_sql(raw) or raw.strip()
            last_sql = sql

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            last_error = result.get("error", "Unknown execution error")

        return last_sql