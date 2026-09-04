"""Generate SQL and repair it using execution errors."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS0G3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = f"Schema:\n{self.schema}\n\nQuestion: {question}\nWrite a single SQL query:"
        raw = self.llm(prompt)
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        sql = bridge.extract_sql(raw)
        if not sql:
            return raw.strip()

        max_attempts = 3
        for _ in range(max_attempts):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "unknown error")
            repair_prompt = (
                f"Schema:\n{self.schema}\n\nQuestion: {question}\n\n"
                f"The previous SQL query was:\n{sql}\n\n"
                f"It failed with the following error:\n{error}\n\n"
                "Please generate a corrected SQL query."
            )
            raw = self.llm(repair_prompt)
            if isinstance(raw, list):
                raw = raw[0] if raw else ""
            new_sql = bridge.extract_sql(raw)
            if new_sql:
                sql = new_sql

        return sql