"""A harness that generates SQL, executes it, classifies errors into syntax/schema/semantics, and applies targeted fixes for up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS2ErrorClassify(SQLHarness):
    def solve(self, question: str) -> str:
        """Generate SQL, execute, classify errors, and apply targeted fixes for up to 2 rounds."""
        # Initial generation
        prompt = f"Schema: {self.schema}\nQuestion: {question}\nSQL:"
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        current_sql = bridge.extract_sql(response)
        
        # Track errors for classification
        last_error = None
        error_type = None
        
        for attempt in range(3):  # Initial + 2 fix rounds
            # Execute current SQL
            result = self.execute(current_sql)
            
            # Success case
            if result["ok"]:
                return current_sql
            
            # Failure: classify error
            last_error = result["error"]
            if "syntax error" in last_error.lower() or "near" in last_error.lower():
                error_type = "syntax"
            elif "no such table" in last_error.lower() or "no such column" in last_error.lower():
                error_type = "schema"
            else:
                error_type = "semantics"
            
            # Stop if this was the last attempt
            if attempt == 2:
                break
            
            # Construct fix-specific prompt
            if error_type == "syntax":
                fix_prompt = (
                    f"The following SQL has a syntax error: {last_error}\n"
                    f"Please correct the syntax. Question: {question}\n"
                    f"Schema: {self.schema}\nSQL:"
                )
            elif error_type == "schema":
                fix_prompt = (
                    f"The following SQL has a schema error: {last_error}\n"
                    f"Please correct using the schema. Question: {question}\n"
                    f"Schema: {self.schema}\nSQL:"
                )
            else:  # semantics
                fix_prompt = (
                    f"The following SQL has a semantic error: {last_error}\n"
                    f"Please correct to return proper results. Question: {question}\n"
                    f"Schema: {self.schema}\nSQL:"
                )
            
            # Generate fixed SQL
            response = self.llm(fix_prompt, system="", temperature=0.0, n=1)
            current_sql = bridge.extract_sql(response)
        
        # Return last attempt (or empty if none)
        return current_sql if current_sql else ""