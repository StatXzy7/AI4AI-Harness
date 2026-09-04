"""Iteratively repairs generated SQL by feeding execution errors back to the LLM for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS2G2(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        max_retries = 3
        base_prompt = f"Given the following database schema:\n{schema}\n\nQuestion: {question}\n\nWrite a SQL query to answer the question."
        
        # First attempt
        prompt = base_prompt
        for attempt in range(max_retries + 1):
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql_text = bridge.extract_sql(response)
            if not sql_text.strip():
                # If extraction fails, treat as an error and retry with a note
                error_msg = "Failed to extract SQL from response."
                if attempt < max_retries:
                    prompt = f"{base_prompt}\n\nPrevious attempt failed to extract SQL. Try again."
                    continue
                else:
                    return sql_text  # return empty string as fallback
            
            result = self.execute(sql_text)
            if result["ok"]:
                return sql_text
            
            # If there's an error and we haven't exhausted retries, prepare a repair prompt
            if attempt < max_retries:
                error_msg = result["error"]
                prompt = f"{base_prompt}\n\nPrevious SQL:\n{sql_text}\nExecution error: {error_msg}\n\nWrite a corrected SQL query."
            else:
                # Last attempt failed, return the last generated SQL
                return sql_text
        
        # Should not reach here, but return empty string as fallback
        return ""