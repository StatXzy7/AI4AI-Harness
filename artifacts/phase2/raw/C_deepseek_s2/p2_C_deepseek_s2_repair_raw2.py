"""Generate SQL, execute it, and if it fails, feed the SQLite error back to the LLM for up to two repair attempts."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        max_repairs = 2
        sql = ""
        last_sql = ""
        error = ""

        def _generate(prompt: str) -> str:
            response = self.llm(
                prompt,
                system="",
                temperature=0.0,
                n=1,
            )
            return bridge.extract_sql(response)

        initial_prompt = (
            f"Given the following SQLite database schema:\n{schema}\n\n"
            f"Write a SQL query to answer the question:\n{question}\n"
            "Return only the SQL query."
        )
        sql = _generate(initial_prompt)
        last_sql = sql

        for attempt in range(max_repairs + 1):
            if attempt > 0:
                repair_prompt = (
                    f"Given the following SQLite database schema:\n{schema}\n\n"
                    f"Question:\n{question}\n\n"
                    f"Your previous SQL query:\n{last_sql}\n\n"
                    f"The execution failed with this SQLite error:\n{error}\n\n"
                    "Fix the SQL query to answer the question correctly. "
                    "Return only the corrected SQL query."
                )
                sql = _generate(repair_prompt)
                last_sql = sql

            result = self.execute(sql)
            if result.get("ok"):
                return sql
            error = result.get("error") or "unknown error"

        return last_sql