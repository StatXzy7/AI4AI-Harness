"""A Text-to-SQL harness that generates SQL with a frozen LLM, executes it, and retries up to 2 times with error feedback on failure."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS1Repair(SQLHarness):
    def solve(self, question: str) -> str:
        """
        Generate SQL from the question and schema, execute it, and if it fails,
        retry up to 2 times by feeding the exact SQLite error back to the LLM.
        """
        system_prompt = (
            "You are a SQL expert. Given a database schema and a question, "
            "write a single SQLite SQL query that answers the question. "
            "Output only the SQL query, nothing else."
        )
        
        max_attempts = 3  # initial attempt + 2 retries
        last_sql = ""
        last_error = ""
        
        for attempt in range(max_attempts):
            if attempt == 0:
                prompt = f"Schema: {self.schema}\nQuestion: {question}"
            else:
                prompt = (
                    f"Schema: {self.schema}\n"
                    f"Question: {question}\n"
                    f"Previous SQL attempt failed with error: {last_error}\n"
                    f"Please fix the SQL and try again. Output only the SQL query."
                )
            
            response = self.llm(prompt, system=system_prompt, temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            
            # Execute the generated SQL
            result = self.execute(sql)
            
            if result["ok"]:
                return sql
            
            # Store for retry feedback
            last_sql = sql
            last_error = result["error"]
        
        # Return the last attempted SQL if all attempts failed
        return last_sql