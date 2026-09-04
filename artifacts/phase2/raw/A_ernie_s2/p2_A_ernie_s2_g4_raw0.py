"""Uses execution error feedback to iteratively repair generated SQL until valid or max retries reached."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AErnieS2G4(SQLHarness):
    def solve(self, question: str) -> str:
        max_retries = 3
        prompt = f"Given the following database schema:\n\n{self.schema}\n\nGenerate a valid SQL query that answers the question: {question}"
        
        for attempt in range(max_retries + 1):
            sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql_text)
            
            if not sql:
                # If extraction failed, treat as an error and retry with repair prompt
                if attempt < max_retries:
                    prompt = f"Failed to extract SQL. Please output ONLY a valid SQL query. Schema:\n{self.schema}\nQuestion: {question}"
                continue
            
            result = self.execute(sql)
            if result["ok"]:
                return sql
            
            # If we have retries left, repair with error feedback
            if attempt < max_retries:
                error_msg = result.get("error", "Unknown execution error")
                prompt = (
                    f"The following SQL query produced an error:\n"
                    f"SQL: {sql}\n"
                    f"Error: {error_msg}\n\n"
                    f"Given the database schema:\n\n{self.schema}\n\n"
                    f"Generate a corrected valid SQL query that answers: {question}"
                )
        
        # If all retries exhausted, return the last generated SQL anyway
        return sql