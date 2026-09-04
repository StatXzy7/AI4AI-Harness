"""Prompt-to-SQL harness using a frozen weak solver with up to two SQLite-error-driven repair retries."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        system_prompt = (
            "You are a SQL generation assistant. Given a database schema and a natural "
            "language question, produce a single SQLite-compatible SQL query that answers "
            "the question. Output only the SQL statement with no explanation, no markdown "
            "fences, and no commentary."
        )

        base_user_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Write exactly one SQLite SQL statement that answers the question. "
            "Return only the SQL."
        )

        max_retries = 2
        last_sql = ""
        last_error = ""

        # First attempt
        response = self.llm(base_user_prompt, system=system_prompt, temperature=0.0, n=1)
        last_sql = bridge.extract_sql(response)
        result = self.execute(last_sql)

        for attempt in range(max_retries):
            if result.get("ok"):
                return last_sql

            last_error = result.get("error", "unknown execution error")
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                f"Previous SQL attempt:\n{last_sql}\n\n"
                f"The previous SQL failed when executed against the database with this error:\n"
                f"{last_error}\n\n"
                "Write a corrected SQLite SQL statement that fixes the error and answers "
                "the question. Return only the SQL."
            )
            response = self.llm(repair_prompt, system=system_prompt, temperature=0.0, n=1)
            last_sql = bridge.extract_sql(response)
            result = self.execute(last_sql)

        if result.get("ok"):
            return last_sql

        return last_sql