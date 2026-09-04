"""Executes LLM-generated SQL against the database and retries up to two times with error feedback if execution fails."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS0Repair(SQLHarness):
    def solve(self, question: str) -> str:
        """Generate SQL, execute it, and retry up to 2 times with error feedback if execution fails."""
        max_attempts = 3  # Initial attempt + 2 retries
        current_error = None
        
        for attempt in range(max_attempts):
            # Build prompt with or without error feedback
            if current_error:
                prompt = (
                    f"Given the following database schema and question, write a SQLite SQL query to answer the question.\n\n"
                    f"Schema: {self.schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Previous SQL attempt failed with the following error: {current_error}\n\n"
                    f"SQL:"
                )
            else:
                prompt = (
                    f"Given the following database schema and question, write a SQLite SQL query to answer the question.\n\n"
                    f"Schema: {self.schema}\n\n"
                    f"Question: {question}\n\n"
                    f"SQL:"
                )
            
            # Generate SQL using LLM
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            
            # Execute the generated SQL
            result = self.execute(sql)
            
            # If execution succeeded, return the SQL
            if result["ok"]:
                return sql
            
            # If execution failed, capture the error for next attempt
            current_error = result["error"]
        
        # If all attempts failed, return the last generated SQL
        return sql