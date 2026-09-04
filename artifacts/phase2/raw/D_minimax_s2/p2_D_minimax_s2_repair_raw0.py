"""Harness that generates SQL with an LLM and repairs it using actual SQLite execution errors up to two retries."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        system_prompt = (
            "You are an expert SQL generator for SQLite. Given a database schema and a natural "
            "language question, produce a single valid SQLite query that answers the question. "
            "Return ONLY the SQL statement, with no explanations, no markdown fences, and no "
            "preamble."
        )

        last_error = None
        last_sql = None

        for attempt in range(3):  # initial attempt + 2 repairs
            if attempt == 0:
                user_prompt = (
                    f"Schema:\n{schema}\n\n"
                    f"Question: {question}\n\n"
                    "Return only the SQL query."
                )
            else:
                user_prompt = (
                    f"Schema:\n{schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Your previous SQL:\n{last_sql}\n\n"
                    f"It failed with this SQLite error:\n{last_error}\n\n"
                    "Produce a corrected SQLite query. Return only the SQL."
                )

            response = self.llm(user_prompt, system=system_prompt, temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            if not sql:
                last_error = "No SQL could be extracted from the model response."
                last_sql = ""
                continue

            execution = self.execute(sql)
            if execution.get("ok"):
                return sql

            last_error = execution.get("error", "Unknown SQLite execution error.")
            last_sql = sql

        return last_sql or ""