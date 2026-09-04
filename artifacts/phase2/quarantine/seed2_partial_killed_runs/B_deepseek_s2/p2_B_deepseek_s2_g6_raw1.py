"""Repair-based SQL generation that retries on execution errors."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G6(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        schema = self.schema
        sql = ""
        error = ""

        for attempt in range(max_attempts):
            if attempt == 0:
                prompt = (
                    f"Generate SQL for the following question.\n"
                    f"Schema:\n{schema}\n"
                    f"Question: {question}\n"
                    f"SQL:"
                )
            else:
                prompt = (
                    f"Generate SQL for the following question.\n"
                    f"Schema:\n{schema}\n"
                    f"Question: {question}\n"
                    f"Previous SQL:\n{sql}\n"
                    f"Execution error: {error}\n"
                    f"Please fix the SQL and return only the corrected SQL.\n"
                    f"SQL:"
                )

            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            if not sql:
                sql = response.strip()

            result = self.execute(sql)
            if result["ok"]:
                return sql
            error = result["error"]

        return sql