"""Generates an initial SQL query, executes it, and upon error classifies the failure type to apply a targeted correction in up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS0ErrorClassify(SQLHarness):
    def solve(self, question: str) -> str:
        # Helper to classify error strings into categories
        def classify_error(error_str: str) -> str:
            error_lower = error_str.lower()
            if any(word in error_lower for word in ["syntax", "near", "unexpected"]):
                return "syntax"
            if any(word in error_lower for word in ["no such table", "no such column", "does not exist"]):
                return "schema"
            if any(word in error_lower for word in ["ambiguous", "type mismatch", "no such function"]):
                return "semantic"
            return "other"

        # Strategy-specific fix instructions per error type
        def get_fix_instruction(error_type: str) -> str:
            if error_type == "syntax":
                return "Please fix the SQL syntax error. Ensure the query is syntactically correct."
            elif error_type == "schema":
                return "Please fix the schema error. Use only valid table and column names from the provided schema."
            elif error_type == "semantic":
                return "Please fix the semantic error. Ensure the query respects data types and relationships."
            else:
                return "Please fix the error in the SQL query."

        max_rounds = 2
        previous_sql = None
        error_str = None
        error_type = None

        for attempt in range(max_rounds):
            if attempt == 0:
                # First round: generate SQL from question and schema
                prompt = (
                    f"Given the following database schema:\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Generate a SQL query to answer the question."
                )
            else:
                # Subsequent round: generate corrected SQL using error information
                fix_instruction = get_fix_instruction(error_type)
                prompt = (
                    f"Given the following database schema:\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Previous SQL query: {previous_sql}\n"
                    f"Error type: {error_type}\n"
                    f"Error details: {error_str}\n\n"
                    f"{fix_instruction}\n"
                    f"Please generate a corrected SQL query."
                )

            # Generate SQL via LLM and extract it
            llm_output = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(llm_output)

            # Execute the generated SQL
            result = self.execute(sql)
            if result["ok"]:
                return sql

            # If execution failed, prepare for next round (if any)
            if attempt == 0:
                error_str = result["error"]
                error_type = classify_error(error_str)
                previous_sql = sql

        # If both rounds fail, return the last generated SQL
        return sql