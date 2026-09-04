"""Repair mechanism: execute generated SQL and feed errors back for up to 3 regeneration attempts."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS0G1(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        prompt = f"Given the schema:\n{self.schema}\n\nQuestion: {question}\n\nWrite a SQL query that answers the question."
        
        for attempt in range(max_attempts):
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            
            result = self.execute(sql)
            if result["ok"]:
                return sql
            
            # If we have attempts left, prepare a repair prompt
            if attempt < max_attempts - 1:
                error_msg = result.get("error", "Unknown error")
                prompt = f"Given the schema:\n{self.schema}\n\nQuestion: {question}\n\nYour previous SQL query had an error:\n{error_msg}\n\nPlease write a corrected SQL query that answers the question."
            else:
                # Last attempt failed, return the last SQL anyway (or could raise, but spec says return final_sql_string)
                return sql
        
        return sql  # fallback, should not reach here