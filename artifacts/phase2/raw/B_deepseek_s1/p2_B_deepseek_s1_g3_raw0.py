"""Generate a SQL query, execute it, and repair it using any execution error as feedback."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS1G3(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        system = "You are a helpful SQL expert. Answer with only SQL."

        initial_prompt = (
            f"Database schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SELECT query that answers the question. Output only the SQL query."
        )
        raw = self.llm(initial_prompt, system=system)
        current_sql = bridge.extract_sql(raw)
        if not current_sql:
            current_sql = "SELECT 1"

        max_attempts = 4
        for _ in range(max_attempts):
            result = self.execute(current_sql)
            if result.get("ok"):
                return current_sql.strip()

            error = result.get("error", "Unknown error")
            repair_prompt = (
                f"Database schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                "The following SQL query was invalid:\n"
                f"{current_sql}\n\n"
                f"Execution error:\n{error}\n\n"
                "Write a corrected SQLite SELECT query that answers the question. Output only the SQL query."
            )
            raw_repair = self.llm(repair_prompt, system=system)
            repaired_sql = bridge.extract_sql(raw_repair)
            if not repaired_sql:
                break
            current_sql = repaired_sql

        return current_sql.strip()