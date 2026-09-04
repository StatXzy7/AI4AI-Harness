"""Repairs SQL queries by executing them and using error feedback to regenerate corrected queries."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS2G5(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: generate initial SQL
        prompt = f"Schema: {self.schema}\nQuestion: {question}\nSQL:"
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)
        
        # Execute and check
        result = self.execute(sql)
        if result["ok"]:
            return sql
        
        # Repair loop: up to 2 additional attempts
        for attempt in range(2):
            error_msg = result.get("error", "Unknown error")
            repair_prompt = (
                f"Schema: {self.schema}\n"
                f"Question: {question}\n"
                f"Previous SQL: {sql}\n"
                f"Error: {error_msg}\n"
                f"Please generate a corrected SQL query:"
            )
            repair_response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(repair_response)
            result = self.execute(sql)
            if result["ok"]:
                return sql
        
        # If all repairs failed, return the last attempt
        return sql