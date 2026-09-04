"""Uses iterative repair by executing generated SQL and feeding errors back for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS2G4(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        last_sql = None
        last_error = None
        
        for attempt in range(max_attempts):
            if attempt == 0:
                prompt = f"Given the schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate the SQL query:"
            else:
                prompt = f"Given the schema:\n{self.schema}\n\nQuestion: {question}\n\nPrevious SQL attempt failed with error: {last_error}\nPrevious SQL: {last_sql}\n\nGenerate a corrected SQL query:"
            
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql_text = bridge.extract_sql(response)
            
            if not sql_text:
                if attempt < max_attempts - 1:
                    last_error = "No SQL extracted from response"
                    continue
                else:
                    return ""
            
            result = self.execute(sql_text)
            
            if result["ok"]:
                return sql_text
            
            last_sql = sql_text
            last_error = result["error"] if result["error"] else "Unknown execution error"
        
        return last_sql if last_sql else ""