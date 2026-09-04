"""Repair mechanism: execute initial SQL, then iteratively regenerate using execution errors until success or max attempts."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS2G1(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        prompt_template = f"""Given the following database schema and question, write a SQL query that answers the question.

Schema:
{self.schema}

Question: {question}

SQL Query:"""
        
        # First attempt
        prompt = prompt_template
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)
        
        for attempt in range(max_attempts):
            result = self.execute(sql)
            if result["ok"]:
                return sql
            
            # If we get here, there was an error. Prepare repair prompt.
            if attempt < max_attempts - 1:  # Not the last attempt
                repair_prompt = f"""The following SQL query failed with the error:

Error: {result["error"]}

Original SQL:
{sql}

Please fix the SQL query to resolve the error. Only output the corrected SQL query.

Schema:
{self.schema}

Question: {question}

Corrected SQL Query:"""
                response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
                sql = bridge.extract_sql(response)
        
        # If we exit the loop, all attempts failed. Return the last SQL anyway.
        return sql