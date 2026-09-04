"""Execute generated SQL and repair it using execution errors for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS0G7(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: generate SQL
        prompt = f"Given the schema:\n{self.schema}\n\nQuestion: {question}\nSQL:"
        sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(sql_text)
        
        # Execute and check
        result = self.execute(sql)
        if result["ok"]:
            return sql
        
        # Repair attempt: feed error back to LLM
        error_msg = result.get("error", "Unknown error")
        repair_prompt = f"Given the schema:\n{self.schema}\n\nQuestion: {question}\n\n" \
                       f"Previous SQL attempt:\n{sql}\n\n" \
                       f"Execution error: {error_msg}\n\n" \
                       f"Please generate a corrected SQL query:"
        repair_text = self.llm(repair_prompt, system="", temperature=0.0, n=1)
        repaired_sql = bridge.extract_sql(repair_text)
        
        # Final execution check
        final_result = self.execute(repaired_sql)
        if final_result["ok"]:
            return repaired_sql
        else:
            # Fallback to repaired SQL even if it fails (or could return original)
            return repaired_sql