"""Implements a repair loop that executes generated SQL and regenerates on errors."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BErnieS1G5(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            # Build prompt with error context if not first attempt
            if attempt == 0:
                prompt = f"Given the database schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate a valid SQL query."
            else:
                prompt = f"Given the database schema:\n{self.schema}\n\nQuestion: {question}\n\nYour previous SQL query failed with error: {last_error}\n\nGenerate a corrected valid SQL query."
            
            # Generate SQL
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql_text = bridge.extract_sql(response)
            
            # Execute the SQL
            result = self.execute(sql_text)
            
            if result.get("ok", False):
                return sql_text
            else:
                last_error = result.get("error", "Unknown error")
        
        # Return the last attempt even if failed (or empty string)
        return sql_text if 'sql_text' in locals() else ""