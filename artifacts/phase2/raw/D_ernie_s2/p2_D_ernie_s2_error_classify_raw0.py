"""A harness that generates SQL, classifies execution errors into syntax/schema/semantics categories, and applies targeted fixes for up to two rounds."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2ErrorClassify(SQLHarness):
    def solve(self, question: str) -> str:
        """Generate SQL, execute, classify errors, and apply strategy-specific fixes for up to 2 rounds."""
        # Initial generation
        prompt = f"""Given the following database schema:
{self.schema}

Question: {question}

Generate a SQL query to answer the question. Output only the SQL query."""
        sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(sql_text)
        
        for attempt in range(2):
            result = self.execute(sql)
            if result["ok"]:
                return sql
            
            # Classify error
            error_type = self._classify_error(result["error"])
            
            # Build correction prompt based on error type
            if error_type == "syntax":
                fix_prompt = f"""The previous SQL query has a syntax error:
{result['error']}

Original question: {question}
Schema:
{self.schema}
Previous SQL: {sql}

Please fix the syntax error and output only the corrected SQL query."""
            elif error_type == "schema":
                fix_prompt = f"""The previous SQL query has a schema error (table/column not found):
{result['error']}

Original question: {question}
Schema:
{self.schema}
Previous SQL: {sql}

Please correct the table/column references and output only the corrected SQL query."""
            else:  # semantics or unknown
                fix_prompt = f"""The previous SQL query has a semantic error:
{result['error']}

Original question: {question}
Schema:
{self.schema}
Previous SQL: {sql}

Please fix the logical/semantic issues and output only the corrected SQL query."""
            
            # Generate corrected SQL
            sql_text = self.llm(fix_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql_text)
        
        # Return last attempt if all fail
        return sql

    @staticmethod
    def _classify_error(error: str) -> str:
        """Classify SQL execution error into syntax, schema, or semantics."""
        error_lower = error.lower()
        if any(keyword in error_lower for keyword in ["syntax error", "near", "unexpected", "missing"]):
            return "syntax"
        elif any(keyword in error_lower for keyword in ["no such table", "no such column", "does not exist", "unknown column"]):
            return "schema"
        else:
            return "semantics"