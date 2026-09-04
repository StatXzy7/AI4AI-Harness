"""A harness that uses a two-step LLM approach to first extract the relevant schema subset and then generate SQL from it."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2CErnieS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Identify relevant tables/columns and extract the linked schema subset.
        prompt1 = f"""Given the following database schema and question, extract the relevant tables and their columns that are needed to answer the question. Then, output the schema for those tables in the following format (one table per line, with columns and types):

TableName: column1 type1, column2 type2, ...

Database Schema:
{self.schema}

Question: {question}

Relevant Schema:
"""
        linked_schema = self.llm(prompt1, system="", temperature=0.0, n=1)
        
        # Step 2: Generate SQL using the linked subset.
        prompt2 = f"""Given the following database schema and question, write the SQL query to answer the question.

Database Schema:
{linked_schema}

Question: {question}

SQL:
"""
        sql_text = self.llm(prompt2, system="", temperature=0.0, n=1)
        
        # Extract and return the final SQL string.
        final_sql = bridge.extract_sql(sql_text)
        return final_sql