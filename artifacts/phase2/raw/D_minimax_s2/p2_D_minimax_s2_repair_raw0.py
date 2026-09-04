"""Self-repair harness that regenerates SQL by feeding back SQLite execution errors up to two retries."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        max_retries = 2
        system_prompt = "You are a Text-to-SQL assistant. Output only a single SQL statement."

        # Initial generation
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQLite-compatible SQL query that answers the question. "
            "Return ONLY the SQL statement with no explanation or formatting."
        )
        response = self.llm(prompt, system=system_prompt, temperature=0.0, n=1)
        sql = bridge.extract_sql(response)

        # Self-repair loop: execute and retry on failure
        for attempt in range(max_retries + 1):
            result = self.execute(sql)

            if result.get("ok"):
                return sql

            # Execution failed; if we have retries left, regenerate with error feedback
            if attempt >= max_retries:
                break

            error_msg = result.get("error", "unknown error")
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Previous SQL attempt:\n{sql}\n\n"
                f"This SQL failed with the following SQLite error:\n{error_msg}\n\n"
                "Write a corrected SQLite-compatible SQL query that fixes the error. "
                "Return ONLY the corrected SQL statement with no explanation or formatting."
            )
            response = self.llm(repair_prompt, system=system_prompt, temperature=0.0, n=1)
            sql = bridge.extract_sql(response)

        # Exhausted retries; return the last generated SQL even though it failed
        return sql