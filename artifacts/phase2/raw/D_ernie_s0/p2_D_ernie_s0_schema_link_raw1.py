"""This harness first uses an LLM to identify relevant tables and columns from the question, then generates SQL against a filtered schema subset."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS0SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Identify tables and columns mentioned in the question
        identify_prompt = f"""Given the following database schema:

{self.schema}

And the question: "{question}"

First, identify all tables and columns mentioned or implied in the question. 
Output in the following format exactly:
Tables: table1, table2, ...
Columns: table1.column1, table2.column2, ...

If no tables or columns are mentioned, output "Tables: none" and "Columns: none"."""
        identify_response = self.llm(identify_prompt, system="", temperature=0.0, n=1)

        # Parse the identification response
        tables = []
        columns = []
        lines = identify_response.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('Tables:'):
                tables_str = line[len('Tables:'):].strip()
                if tables_str.lower() != 'none':
                    tables = [t.strip() for t in tables_str.split(',') if t.strip()]
            elif line.startswith('Columns:'):
                cols_str = line[len('Columns:'):].strip()
                if cols_str.lower() != 'none':
                    columns = [c.strip() for c in cols_str.split(',') if c.strip()]

        # If no tables identified, fall back to the full schema
        if not tables and not columns:
            subset_schema = self.schema
        else:
            # Build a subset schema containing only the identified tables
            # Split the full schema into individual CREATE TABLE statements
            parts = self.schema.split('CREATE TABLE')
            subset_parts = []
            for part in parts[1:]:  # skip the part before the first CREATE TABLE
                # Extract the table name (first word after CREATE TABLE)
                table_name = part.split()[0].strip().rstrip('(')
                if table_name in tables:
                    # Reconstruct the full CREATE TABLE statement for this table
                    subset_parts.append('CREATE TABLE' + part)
            subset_schema = '\n'.join(subset_parts)
            if not subset_schema:  # if no matching tables found, use full schema
                subset_schema = self.schema

        # Step 2: Generate SQL using the subset schema
        sql_prompt = f"""Given the following database schema (only the relevant tables and columns):

{subset_schema}

And the question: "{question}"

Write a SQL query that answers the question. Use only the tables and columns provided.
Output the SQL query only, without any explanation."""
        sql_response = self.llm(sql_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(sql_response)
        return final_sql