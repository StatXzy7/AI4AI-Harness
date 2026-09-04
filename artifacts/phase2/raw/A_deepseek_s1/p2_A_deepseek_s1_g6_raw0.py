"""Generate a candidate SQL query, execute it, and feed any execution error back to the LLM to produce a repaired query."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS1G6(SQLHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite engineer. "
            "Given a database schema and a question, write one valid SQLite query. "
            "Output only SQL without markdown or explanation."
        )

        initial_prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write the SQL query:"
        )
        initial_raw = self.llm(initial_prompt, system=system, temperature=0.0, n=1)
        sql = bridge.extract_sql(initial_raw)

        if not sql:
            return initial_raw.strip()

        result = self.execute(sql)

        if result.get("ok"):
            return sql

        error = result.get("error", "unknown execution error")

        repair_prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Previous SQL:\n{sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Write a corrected SQLite query. Output only SQL without markdown or explanation."
        )
        repair_raw = self.llm(repair_prompt, system=system, temperature=0.0, n=1)
        repaired_sql = bridge.extract_sql(repair_raw)

        if not repaired_sql:
            return sql

        self.execute(repaired_sql)
        return repaired_sql