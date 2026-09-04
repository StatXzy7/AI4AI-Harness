"""This harness uses a repair mechanism: it executes generated SQL and feeds execution errors back to the LLM for regeneration up to a fixed number of attempts."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS1G2(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        for attempt in range(max_attempts):
            # Generate initial SQL
            prompt = f"Schema: {self.schema}\nQuestion: {question}\nSQL:"
            sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql_text)
            
            # Execute the SQL
            result = self.execute(sql)
            
            # If successful, return the SQL
            if result["ok"]:
                return sql
            
            # If failed and we have attempts left, prepare repair prompt
            if attempt < max_attempts - 1:
                error_msg = result["error"] if result["error"] else "Unknown error"
                repair_prompt = (
                    f"Schema: {self.schema}\n"
                    f"Question: {question}\n"
                    f"Previous SQL: {sql}\n"
                    f"Error: {error_msg}\n"
                    f"Please repair the SQL to fix the error:"
                )
                sql_text = self.llm(repair_prompt, system="", temperature=0.0, n=1)
                sql = bridge.extract_sql(sql_text)
        
        # Return the last generated SQL if all attempts failed
        return sql