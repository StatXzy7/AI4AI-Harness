"""Generates SQL via LLM, executes it, and repairs up to two times using exact error feedback."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        # Initial prompt for first SQL generation
        prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate a SQL query to answer the question."
        
        prev_sql = None
        prev_error = None
        
        for attempt in range(3):  # Initial + up to 2 repairs
            if attempt == 0:
                # First attempt: generate from scratch
                response = self.llm(prompt, system="", temperature=0.0, n=1)
            else:
                # Repair attempt: include previous SQL and exact error
                repair_prompt = (
                    f"Given the following database schema:\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Previous SQL: {prev_sql}\n"
                    f"Error: {prev_error}\n\n"
                    f"Generate a corrected SQL query."
                )
                response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            
            # Extract SQL from LLM response
            sql = bridge.extract_sql(response)
            
            # Execute the generated SQL
            result = self.execute(sql)
            
            if result["ok"]:
                return sql  # Success: return working SQL
            else:
                # Store failure details for next repair attempt
                prev_sql = sql
                prev_error = result["error"]
        
        # All attempts failed: return last generated SQL (or empty if none)
        return prev_sql if prev_sql is not None else ""