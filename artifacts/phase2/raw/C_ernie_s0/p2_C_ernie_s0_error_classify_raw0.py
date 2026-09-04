"""Executes Text-to-SQL with error classification and strategy-specific fixes across up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS0ErrorClassify(SQLHarness):
    def solve(self, question: str) -> str:
        """Generate SQL, execute it, classify failures, and apply targeted fixes for up to 2 rounds."""
        # Round 1: initial generation
        prompt = (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Generate a SQL query to answer the question."
        )
        sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(sql_text)
        result = self.execute(sql)

        if result["ok"]:
            return sql

        # Classify the error from the first attempt
        error = result["error"].lower()
        if "syntax" in error or "near" in error or "unrecognized" in error:
            error_class = "syntax"
        elif "no such table" in error or "no such column" in error or "does not exist" in error:
            error_class = "schema"
        else:
            error_class = "semantics"

        # Round 2: targeted fix based on error class
        if error_class == "syntax":
            fix_prompt = (
                f"Given the following database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"The previous SQL query had a syntax error: {result['error']}\n\n"
                f"Please fix the syntax error and generate a correct SQL query."
            )
        elif error_class == "schema":
            fix_prompt = (
                f"Given the following database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"The previous SQL query had a schema error: {result['error']}\n\n"
                f"Please use only the tables and columns that exist in the schema and generate a correct SQL query."
            )
        else:  # semantics
            fix_prompt = (
                f"Given the following database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"The previous SQL query returned no results or had a semantic error: {result['error']}\n\n"
                f"Please adjust the query to return meaningful results and generate a correct SQL query."
            )

        sql_text2 = self.llm(fix_prompt, system="", temperature=0.0, n=1)
        sql2 = bridge.extract_sql(sql_text2)
        result2 = self.execute(sql2)

        if result2["ok"]:
            return sql2

        # Return the last generated SQL even if it failed (as per harness contract)
        return sql2