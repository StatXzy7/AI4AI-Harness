"""Uses a repair mechanism that executes generated SQL and feeds back execution errors for regeneration up to three attempts."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS2G4(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        last_sql = ""
        last_error = ""
        
        for attempt in range(max_attempts):
            if attempt == 0:
                prompt = f"Given the following schema: {self.schema}\nQuestion: {question}\nGenerate a SQL query that answers the question."
            else:
                prompt = f"Given the following schema: {self.schema}\nQuestion: {question}\nPrevious SQL query: {last_sql}\nExecution error: {last_error}\nGenerate a corrected SQL query."
            
            sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql_text)
            last_sql = sql
            
            result = self.execute(sql)
            if result["ok"]:
                return sql
            last_error = result["error"]
        
        return last_sql