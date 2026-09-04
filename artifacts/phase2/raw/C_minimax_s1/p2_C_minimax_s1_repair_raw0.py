"""P2P2C (Plan-Pick-Probe-Correct) Minimax-S1 repair loop that executes each candidate SQL and feeds SQLite errors back into the next regeneration."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS1Repair(SQLHarness):
    def solve(self, question: str) -> str:
        max_repairs = 2
        last_sql = ""
        last_error = ""

        # Initial generation (C1: Compose)
        system_prompt = (
            "You are an expert SQL generator for SQLite. Given the schema and a "
            "natural-language question, produce a single SQL query that answers it. "
            "Return ONLY the SQL, with no commentary or markdown fences."
        )
        user_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Generate the SQL query."
        )
        raw = self.llm(user_prompt, system=system_prompt, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw) or raw.strip()
        last_sql = sql

        # Repair loop
        for attempt in range(max_repairs + 1):
            result = self.execute(last_sql)
            if result.get("ok"):
                return last_sql
            last_error = result.get("error", "unknown error")

            if attempt >= max_repairs:
                break

            # Feed the exact SQLite error back into regeneration (C2: Correct)
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Previous SQL:\n{last_sql}\n\n"
                f"SQLite execution error:\n{last_error}\n\n"
                "Produce a corrected SQL query that fixes the error. "
                "Return ONLY the corrected SQL."
            )
            raw_retry = self.llm(repair_prompt, system=system_prompt, temperature=0.0, n=1)
            new_sql = bridge.extract_sql(raw_retry) or raw_retry.strip()
            if not new_sql:
                break
            last_sql = new_sql

        return last_sql