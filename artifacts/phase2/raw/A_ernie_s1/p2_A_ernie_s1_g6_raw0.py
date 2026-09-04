"""Harness that uses error-driven repair: executes generated SQL and feeds execution errors back to the LLM for correction."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS1G6(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        for attempt in range(max_attempts):
            # Generate initial SQL
            prompt = f"Schema: {self.schema}\nQuestion: {question}\nSQL:"
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            
            # Execute SQL
            result = self.execute(sql)
            if result["ok"]:
                return sql
            
            # If error and not last attempt, repair
            if attempt < max_attempts - 1:
                repair_prompt = (
                    f"Schema: {self.schema}\n"
                    f"Question: {question}\n"
                    f"Previous SQL: {sql}\n"
                    f"Error: {result['error']}\n"
                    f"Corrected SQL:"
                )
                repair_response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
                sql = bridge.extract_sql(repair_response)
            else:
                # Last attempt failed, return best we have
                return sql
        
        # Should not reach here, but return last sql
        return sql