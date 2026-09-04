"""Single-pass generation with execution repair: regenerate on SQL execution failure up to 2 times."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

MAX_REPAIRS = 2


class P2P2BMinimaxS0G5(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = (
            "Given the database schema below, write a single SQL query that answers the question.\n"
            "Return ONLY the SQL, no commentary, no markdown fences.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        sql = bridge.extract_sql(
            self.llm(prompt, system="You are a precise Text-to-SQL generator.", temperature=0.0, n=1)
        )

        last_error = ""
        for _ in range(MAX_REPAIRS):
            result = self.execute(sql)
            if result.get("ok"):
                return sql
            last_error = result.get("error", "unknown execution error")
            repair_prompt = (
                "The following SQL produced an execution error against the database.\n"
                "Fix the SQL so it executes successfully and answers the original question.\n"
                "Return ONLY the corrected SQL, no commentary, no markdown fences.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Failed SQL:\n{sql}\n\n"
                f"Execution error:\n{last_error}\n\n"
                "Corrected SQL:"
            )
            sql = bridge.extract_sql(
                self.llm(repair_prompt, system="You are a precise Text-to-SQL repair engine.", temperature=0.0, n=1)
            )

        return sql