"""Repair mechanism: execute initial SQL, feed execution errors back to LLM for correction up to two attempts."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS1G0(SQLHarness):
    def solve(self, question: str) -> str:
        # Initial generation with schema and question
        prompt = f"Given the database schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate a single SQL query that answers the question."
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)
        
        # First execution attempt
        result = self.execute(sql)
        
        # If execution fails, attempt repair with error feedback
        if not result["ok"]:
            repair_prompt = f"Given the database schema:\n{self.schema}\n\nQuestion: {question}\n\nThe following SQL query failed with error: {result['error']}\n\nGenerate a corrected SQL query that answers the question."
            repair_response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(repair_response)
            
            # Second execution attempt with repaired query
            result = self.execute(sql)
            
            # If still fails, attempt one more repair (optional third attempt)
            if not result["ok"]:
                repair_prompt2 = f"Given the database schema:\n{self.schema}\n\nQuestion: {question}\n\nThe previous corrected query still failed with error: {result['error']}\n\nGenerate a final corrected SQL query."
                repair_response2 = self.llm(repair_prompt2, system="", temperature=0.0, n=1)
                sql = bridge.extract_sql(repair_response2)
        
        return sql