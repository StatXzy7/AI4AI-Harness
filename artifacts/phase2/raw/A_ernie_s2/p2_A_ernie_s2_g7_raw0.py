"""Repair mechanism: execute generated SQL and iteratively fix errors by feeding them back to the LLM."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS2G7(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        for attempt in range(max_attempts):
            # Generate initial SQL
            prompt = f"Question: {question}\nSchema: {self.schema}\nGenerate SQL:"
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            
            # Execute SQL
            result = self.execute(sql)
            if result["ok"]:
                return sql
            
            # If error and not last attempt, repair
            if attempt < max_attempts - 1:
                error_msg = result.get("error", "Unknown error")
                repair_prompt = (
                    f"Question: {question}\n"
                    f"Schema: {self.schema}\n"
                    f"Previous SQL: {sql}\n"
                    f"Error: {error_msg}\n"
                    f"Fix the SQL to resolve the error:"
                )
                response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
                sql = bridge.extract_sql(response)
        
        # Return last attempt even if failed (as per requirement to return final_sql_string)
        return sql