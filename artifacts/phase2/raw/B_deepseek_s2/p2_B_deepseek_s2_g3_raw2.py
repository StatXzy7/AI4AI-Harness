"""Generate a SQL query, execute it, and repair it using execution errors as feedback."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G3(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are a SQL expert. Return only the SQL query."
        prompt = (
            "Given the database schema:\n"
            f"{self.schema}\n\n"
            f"Write a SQL query that answers the question:\n{question}\n\n"
            "Return only the SQL query."
        )
        sql = bridge.extract_sql(self.llm(prompt, system=system, temperature=0.0, n=1)).strip()
        
        max_attempts = 4  # initial query + up to 3 error-driven repairs
        for attempt in range(max_attempts):
            if not sql:
                break
            
            result = self.execute(sql)
            if result.get("ok"):
                return sql
            
            # No repair after the final attempt.
            if attempt == max_attempts - 1:
                break
            
            error = result.get("error", "Unknown error")
            repair_prompt = (
                "The following SQL query failed when executed:\n"
                f"{sql}\n\n"
                f"Database error:\n{error}\n\n"
                "Using the schema and question below, write a corrected SQL query.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                "Return only the corrected SQL query."
            )
            sql = bridge.extract_sql(
                self.llm(repair_prompt, system=system, temperature=0.0, n=1)
            ).strip()
        
        return sql or ""