"""Implements a repair mechanism that executes generated SQL and feeds execution errors back to the LLM for regeneration up to 3 attempts."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS0G5(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        # First attempt: generate SQL from schema and question
        prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nWrite a SQL query to answer the question."
        sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(sql_text)
        
        for attempt in range(max_attempts):
            result = self.execute(sql)
            if result["ok"]:
                return sql
            # If execution failed, repair the SQL using the error message
            if attempt < max_attempts - 1:  # Not the last attempt
                repair_prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nPrevious SQL query:\n{sql}\n\nExecution error: {result['error']}\n\nFix the SQL query."
                sql_text = self.llm(repair_prompt, system="", temperature=0.0, n=1)
                sql = bridge.extract_sql(sql_text)
            else:
                # Last attempt failed, return the last generated SQL
                return sql
        # This line should never be reached due to loop structure, but return last SQL as fallback
        return sql