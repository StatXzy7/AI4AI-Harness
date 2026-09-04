"""Executes generated SQL and, if execution fails, feeds the error back to the LLM for repair."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2BDeepseekS2G5(SQLHarness):
    def solve(self, question: str) -> str:
        """
        Generate SQL, execute it, and repair on errors up to a fixed number of attempts.
        """
        max_attempts = 3
        system_msg = "You are a helpful assistant that writes SQL queries."
        prompt = self._make_initial_prompt(question)
        
        last_sql = ""
        for attempt in range(max_attempts):
            # Generate SQL from the LLM
            response = self.llm(prompt, system=system_msg, temperature=0.0, n=1)
            
            # Extract SQL from the response; fallback to raw response if extraction returns empty
            sql = bridge.extract_sql(response) or response.strip()
            if not sql:
                # If still empty, use a placeholder to avoid crashing
                sql = "SELECT"
            last_sql = sql
            
            # Execute the SQL
            result = self.execute(sql)
            
            # If execution succeeded, return the SQL
            if result.get("ok"):
                return sql
            
            # Execution failed: prepare repair prompt for next iteration
            error = result.get("error", "Unknown error")
            prompt = self._make_repair_prompt(question, sql, error)
        
        # Return the last generated SQL even if all attempts failed
        return last_sql

    def _make_initial_prompt(self, question: str) -> str:
        """Create the initial prompt asking for a SQL query."""
        return (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write the SQL query that answers the question. Return only the SQL query."
        )

    def _make_repair_prompt(self, question: str, failed_sql: str, error: str) -> str:
        """Create a prompt to repair a failed SQL query."""
        return (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"The following SQL query was generated but produced an error when executed:\n"
            f"SQL: {failed_sql}\n"
            f"Error: {error}\n\n"
            "Please provide a corrected SQL query that answers the question. Return only the SQL query."
        )