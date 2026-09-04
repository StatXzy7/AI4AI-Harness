"""This harness employs a repair mechanism that generates an initial SQL query, executes it, and upon failure regenerates the query with error feedback for up to two repair attempts."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS1G5(SQLHarness):
    def solve(self, question: str) -> str:
        max_repairs = 2
        # Build initial prompt for first SQL generation
        prompt = f"Given the following database schema:\n\n{self.schema}\n\nQuestion: {question}\n\nGenerate the SQL query to answer the question."
        # Generate initial SQL query
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        current_sql = bridge.extract_sql(response)
        
        # Attempt execution and repair up to max_repairs times
        for attempt in range(max_repairs + 1):
            # Execute current SQL
            result = self.execute(current_sql)
            if result["ok"]:
                return current_sql
            
            # If last attempt, break without further repair
            if attempt == max_repairs:
                break
            
            # Construct repair prompt with error context
            repair_prompt = f"The following SQL query failed with error: {result['error']}\n\n"
            repair_prompt += f"Original question: {question}\n\n"
            repair_prompt += f"Database schema:\n{self.schema}\n\n"
            repair_prompt += f"Previous SQL: {current_sql}\n\n"
            repair_prompt += "Please fix the SQL query to resolve the error."
            
            # Generate repaired SQL
            repair_response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            current_sql = bridge.extract_sql(repair_response)
        
        # Return last generated SQL even if execution failed
        return current_sql