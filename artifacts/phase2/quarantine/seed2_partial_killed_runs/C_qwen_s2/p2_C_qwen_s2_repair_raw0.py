"""Generates SQL, executes it, and if execution fails regenerates up to two times using the exact SQLite error."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are an expert SQLite SQL programmer. Return only a single SQL query."

        last_sql = ""
        last_error = ""

        # Initial attempt + up to 2 repair attempts.
        for attempt in range(3):
            if attempt == 0:
                prompt = (
                    "Write a single SQLite SQL query that answers the question using the schema.\n\n"
                    f"Schema:\n{self.schema}\n\n"
                    f"Question:\n{question}\n\n"
                    "Return only the SQL query."
                )
            else:
                previous_sql = last_sql if last_sql else "<no SQL was extracted>"
                prompt = (
                    "The previous SQL query failed. Fix it so it executes successfully.\n\n"
                    f"SQLite error:\n{last_error}\n\n"
                    f"Schema:\n{self.schema}\n\n"
                    f"Question:\n{question}\n\n"
                    f"Previous SQL:\n{previous_sql}\n\n"
                    "Return only the SQL query."
                )

            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
            raw = raw if isinstance(raw, str) else str(raw)

            extracted = bridge.extract_sql(raw)
            sql = extracted.strip() if isinstance(extracted, str) else ""

            if not sql:
                if not last_error:
                    last_error = "No SQL could be extracted from the model response."
                continue

            last_sql = sql

            try:
                result = self.execute(sql)
            except Exception as exc:
                last_error = str(exc)
                continue

            if isinstance(result, dict) and result.get("ok"):
                return sql

            error = ""
            if isinstance(result, dict):
                error = str(result.get("error", ""))

            last_error = error if error else "SQLite execution failed."

        return last_sql