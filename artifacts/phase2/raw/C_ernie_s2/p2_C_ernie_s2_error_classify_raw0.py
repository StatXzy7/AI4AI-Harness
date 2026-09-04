"""Implements a Text-to-SQL harness that generates SQL, executes it, classifies failures into syntax/schema/semantics errors, and applies targeted fixes for up to two repair rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS2ErrorClassify(SQLHarness):
    def solve(self, question: str) -> str:
        """Generate SQL, execute it, classify errors, and apply targeted fixes for up to two rounds."""
        # Initial generation attempt
        prompt = f"""You are a Text-to-SQL model. Given the following database schema and question, generate a SQL query that answers the question.

Schema:
{self.schema}

Question: {question}

SQL:"""
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)
        
        # Execution and error handling loop (up to 3 total attempts: initial + 2 fixes)
        for attempt in range(3):
            result = self.execute(sql)
            if result["ok"]:
                return sql
            
            error = result["error"].lower()
            
            # Classify error type
            if any(kw in error for kw in ["syntax error", "near", "unexpected", "missing"]):
                error_type = "syntax"
            elif any(kw in error for kw in ["table", "column", "does not exist", "unknown"]):
                error_type = "schema"
            else:
                error_type = "semantics"
            
            # If this is the last attempt, return the current SQL anyway
            if attempt == 2:
                return sql
            
            # Build fix prompt with error-specific guidance
            fix_prompt = f"""You are a Text-to-SQL model. The previous SQL query failed with a {error_type} error. Please fix the query.

Schema:
{self.schema}

Question: {question}

Previous SQL: {sql}

Error: {result['error']}

Error type: {error_type}

Fix instructions:
- For syntax errors: Ensure proper SQL syntax, correct punctuation, and valid keywords.
- For schema errors: Use only table and column names that exist in the provided schema.
- For semantics errors: Ensure the query logic correctly answers the question, with proper joins and conditions.

Fixed SQL:"""
            
            # Generate fixed SQL
            fix_response = self.llm(fix_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(fix_response)
        
        return sql  # Fallback (should not be reached due to loop structure)