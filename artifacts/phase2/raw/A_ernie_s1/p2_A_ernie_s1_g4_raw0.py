"""Repair mechanism that executes generated SQL and uses error feedback to regenerate corrected queries."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS1G4(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: generate initial SQL
        prompt = f"Given the following database schema:\n\n{self.schema}\n\nWrite a SQL query to answer: {question}"
        sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(sql_text)
        
        # Execute the initial SQL
        result = self.execute(sql)
        if result["ok"]:
            return sql
        
        # If execution failed, attempt repair using error feedback
        error_msg = result.get("error", "Unknown error")
        repair_prompt = f"The following SQL query failed with error: {error_msg}\n\n" \
                        f"Original question: {question}\n\n" \
                        f"Failed SQL: {sql}\n\n" \
                        f"Please provide a corrected SQL query that addresses the error."
        repair_text = self.llm(repair_prompt, system="", temperature=0.0, n=1)
        repaired_sql = bridge.extract_sql(repair_text)
        
        # Execute the repaired SQL (even if it fails, we return it as the final attempt)
        # Optionally, we could check again, but we limit to one repair per spec.
        return repaired_sql