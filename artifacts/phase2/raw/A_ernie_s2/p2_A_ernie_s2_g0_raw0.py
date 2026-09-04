"""This harness uses a repair mechanism that executes the initial SQL and then repairs it using error feedback if execution fails."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS2G0(SQLHarness):
    def solve(self, question: str) -> str:
        # Initial generation
        prompt = f"Question: {question}\nSchema: {self.schema}\nSQL:"
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)
        
        # Try execution and repair up to 2 times
        for attempt in range(3):
            result = self.execute(sql)
            if result["ok"]:
                return sql
            # If failed, prepare repair prompt
            if attempt < 2:  # Only repair up to 2 times
                error_feedback = f"Error: {result['error']}\nPrevious SQL: {sql}"
                repair_prompt = f"Question: {question}\nSchema: {self.schema}\n{error_feedback}\nCorrected SQL:"
                repair_response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
                sql = bridge.extract_sql(repair_response)
            else:
                # After max attempts, return the last SQL (even if failed)
                break
        return sql