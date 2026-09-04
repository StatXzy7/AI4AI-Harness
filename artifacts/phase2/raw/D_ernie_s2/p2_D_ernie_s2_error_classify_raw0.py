"""A harness that generates SQL via a frozen LLM, executes it, classifies errors into syntax/schema/semantics, and applies targeted fixes for up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS2ErrorClassify(SQLHarness):
    def solve(self, question: str) -> str:
        # Initial generation
        prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate a SQL query to answer the question."
        sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
        current_sql = bridge.extract_sql(sql_text)
        
        # Execute and check
        result = self.execute(current_sql)
        if result["ok"]:
            return current_sql
        
        # Up to two rounds of error classification and fixing
        for round_num in range(2):
            error_msg = result["error"]
            error_type = self._classify_error(error_msg)
            
            # Construct fix prompt based on error type
            fix_prompt = self._build_fix_prompt(question, current_sql, error_msg, error_type)
            fix_text = self.llm(fix_prompt, system="", temperature=0.0, n=1)
            current_sql = bridge.extract_sql(fix_text)
            
            # Execute the fixed SQL
            result = self.execute(current_sql)
            if result["ok"]:
                return current_sql
        
        # Return the last generated SQL even if still failing
        return current_sql
    
    def _classify_error(self, error_msg: str) -> str:
        """Classify error into 'syntax', 'schema', or 'semantics' using heuristics."""
        error_lower = error_msg.lower()
        
        # Syntax error indicators
        if any(word in error_lower for word in ["syntax", "near", "unexpected", "missing", "invalid", "parse"]):
            return "syntax"
        
        # Schema error indicators
        if any(word in error_lower for word in ["column", "table", "does not exist", "unknown", "no such", "relation"]):
            return "schema"
        
        # Default to semantics (type errors, division by zero, etc.)
        return "semantics"
    
    def _build_fix_prompt(self, question: str, current_sql: str, error_msg: str, error_type: str) -> str:
        """Build a prompt for the LLM to fix the SQL based on error type."""
        base = f"Original question: {question}\nOriginal SQL: {current_sql}\nExecution error: {error_msg}\n"
        
        if error_type == "syntax":
            return base + "The SQL has a syntax error. Please correct the syntax and output a valid SQL query."
        elif error_type == "schema":
            return base + f"The SQL has a schema error (e.g., wrong table or column name). Given the schema:\n{self.schema}\nPlease fix the SQL to use correct table/column names."
        else:  # semantics
            return base + "The SQL has a semantic error (e.g., type mismatch, invalid operation). Please adjust the query logic to answer the question correctly."