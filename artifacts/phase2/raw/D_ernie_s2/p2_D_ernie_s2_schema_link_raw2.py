"""Implements a two-step Text-to-SQL harness that first identifies relevant schema elements via LLM, then generates SQL against that linked subset."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Identify relevant tables/columns from the schema
        schema_link_prompt = (
            f"Given the following database schema and question, identify the tables and columns "
            f"that are relevant to answering the question. Output only the table names and their "
            f"associated column names in the format: 'table1: col1, col2; table2: col3, col4'. "
            f"Do not include any other text.\n\n"
            f"Schema: {self.schema}\n\n"
            f"Question: {question}"
        )
        
        link_response = self.llm(schema_link_prompt, system="", temperature=0.0, n=1)
        
        # Step 2: Generate SQL using only the linked subset
        sql_gen_prompt = (
            f"Given the following database schema and question, write a SQL query that answers "
            f"the question. Use ONLY the tables and columns identified below. Do not use any other "
            f"tables or columns from the schema.\n\n"
            f"Relevant schema subset: {link_response}\n\n"
            f"Full schema for reference: {self.schema}\n\n"
            f"Question: {question}\n\n"
            f"SQL:"
        )
        
        sql_response = self.llm(sql_gen_prompt, system="", temperature=0.0, n=1)
        
        # Extract and return the SQL
        final_sql = bridge.extract_sql(sql_response)
        return final_sql