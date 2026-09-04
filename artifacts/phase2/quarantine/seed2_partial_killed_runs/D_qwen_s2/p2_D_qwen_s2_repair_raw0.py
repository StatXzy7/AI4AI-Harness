"""Generate SQL, execute it, and repair up to two times by feeding the exact SQLite error back to the model."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are an expert SQLite SQL programmer. Return only one executable SQL query."
        context = f"Schema:\n{self.schema}\n\nQuestion: {question}\n\n"

        last_sql = ""
        last_error = ""

        # Initial attempt + up to 2 repair attempts.
        for attempt in range(3):
            if attempt == 0:
                prompt = (
                    context
                    + "Write a single SQLite SQL query that answers the question. Return only SQL."
                )
            else:
                prompt = (
                    context
                    + "The previous SQL query failed when executed in SQLite.\n"
                    + f"Previous SQL:\n{last_sql}\n\n"
                    + f"Exact SQLite error:\n{last_error}\n\n"
                    + "Fix the query so it executes successfully. Return only the corrected SQL."
                )

            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
            raw = "" if raw is None else str(raw)

            sql = bridge.extract_sql(raw) or ""
            sql = sql.strip()

            if not sql:
                last_sql = raw.strip()
                last_error = "No SQL statement could be extracted from the response."
                continue

            last_sql = sql
            result = self.execute(sql)

            if isinstance(result, dict) and result.get("ok"):
                return sql

            if isinstance(result, dict):
                last_error = result.get("error") or "Unknown execution error"
            else:
                last_error = "Unknown execution error"

        return last_sql