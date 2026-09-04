"""Repair-based text-to-SQL harness that retries generation after execution errors."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS1G4(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are a SQL expert. Return only a syntactically correct SQL query, without explanation."

        base_prompt = f"Schema:\n{self.schema}\n\nQuestion: {question}\n\nSQL:"
        raw = self.llm(base_prompt, system=system, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw) or raw.strip()

        result = self.execute(sql)
        if result.get("ok"):
            return sql

        for _ in range(2):
            error = result.get("error", "unknown execution error")
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Your previous SQL:\n{sql}\n\n"
                f"Execution error:\n{error}\n\n"
                "Please produce a corrected SQL query. Return only SQL."
            )
            raw = self.llm(repair_prompt, system=system, temperature=0.0, n=1)
            repaired_sql = bridge.extract_sql(raw) or raw.strip()
            if not repaired_sql:
                break
            sql = repaired_sql
            result = self.execute(sql)
            if result.get("ok"):
                return sql

        return sql