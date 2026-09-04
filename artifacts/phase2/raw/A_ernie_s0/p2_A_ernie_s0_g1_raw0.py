"""Uses iterative self-repair: generates SQL, executes it, and regenerates on failure using the error feedback."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AErnieS0G1(SQLHarness):
    def solve(self, question: str) -> str:
        max_retries = 3
        prompt = f"Given the following database schema:\n\n{self.schema}\n\nQuestion: {question}\n\nGenerate a valid SQL query that answers the question. Output only the SQL query."
        
        for attempt in range(max_retries + 1):
            raw = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(raw)
            
            result = self.execute(sql)
            if result.get("ok", False):
                return sql
            
            if attempt < max_retries:
                error_msg = result.get("error", "Unknown error")
                prompt = f"Given the following database schema:\n\n{self.schema}\n\nQuestion: {question}\n\nYour previous SQL query failed with this error:\n{error_msg}\n\nGenerate a corrected valid SQL query. Output only the SQL query."
        
        return sql