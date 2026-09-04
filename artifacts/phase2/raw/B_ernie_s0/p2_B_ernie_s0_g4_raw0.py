"""Repair mechanism: execute SQL and feed errors back to LLM for regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS0G4(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        # Initial prompt for first attempt
        prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nSQL:"
        sql = None
        for attempt in range(max_attempts):
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            result = self.execute(sql)
            if result["ok"]:
                return sql
            # Prepare repair prompt for next attempt
            error_msg = result["error"]
            prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nPrevious SQL attempt: {sql}\nError: {error_msg}\n\nPlease provide a corrected SQL:"
        # If all attempts failed, return the last SQL
        return sql