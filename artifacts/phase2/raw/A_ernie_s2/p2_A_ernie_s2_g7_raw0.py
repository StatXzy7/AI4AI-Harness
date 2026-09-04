"""This harness uses a repair mechanism that executes generated SQL and feeds errors back to the LLM for correction."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS2G7(SQLHarness):
    def solve(self, question: str) -> str:
        max_repairs = 2
        
        # Initial SQL generation
        prompt = f"Given the following database schema:\n\n{self.schema}\n\nQuestion: {question}\n\nWrite a SQL query to answer the question."
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)
        
        # Execute and check
        result = self.execute(sql)
        if result["ok"]:
            return sql
        
        # Repair loop
        for attempt in range(max_repairs):
            # Create repair prompt with error feedback
            repair_prompt = f"Given the following database schema:\n\n{self.schema}\n\nQuestion: {question}\n\nYour previous SQL query:\n{sql}\n\nError message: {result['error']}\n\nPlease fix the SQL query to resolve the error."
            repair_response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(repair_response)
            
            # Execute repaired SQL
            result = self.execute(sql)
            if result["ok"]:
                return sql
        
        # Return last attempt even if failed (as per requirement to return a string)
        return sql