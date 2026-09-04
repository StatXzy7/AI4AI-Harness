"""
Uses a two-step LLM strategy: first extracts relevant tables/columns from the question, then generates SQL using only that linked subset.
"""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2CErnieS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Identify relevant tables and columns from the question
        identify_prompt = f"""Given the following database schema and question, identify the tables and columns that are relevant to answering the question.

Schema:
{self.schema}

Question: {question}

Output in the following format (one table per line, columns separated by commas):
Tables: table1, table2, ...
Columns: table1.col1, table1.col2, table2.col1, ...

Only include tables and columns that are explicitly mentioned or implied by the question. Do not include tables/columns that are not needed."""
        
        identify_response = self.llm(identify_prompt, system="", temperature=0.0, n=1)
        
        # Parse the identified tables and columns
        lines = identify_response.strip().split('\n')
        tables = []
        columns = []
        
        for line in lines:
            line = line.strip()
            if line.lower().startswith('tables:'):
                tables_str = line.split(':', 1)[1].strip()
                if tables_str:
                    tables = [t.strip() for t in tables_str.split(',')]
            elif line.lower().startswith('columns:'):
                cols_str = line.split(':', 1)[1].strip()
                if cols_str:
                    columns = [c.strip() for c in cols_str.split(',')]
        
        # Build linked subset schema from identified tables/columns
        # Parse the full schema to extract only the relevant parts
        subset_schema_parts = []
        schema_lines = self.schema.strip().split('\n')
        current_table = None
        current_columns = []
        
        for line in schema_lines:
            line = line.strip()
            if line.upper().startswith('CREATE TABLE'):
                # Save previous table if any
                if current_table and current_table in tables:
                    subset_schema_parts.append(f"CREATE TABLE {current_table} ({', '.join(current_columns)})")
                
                # Extract table name
                table_name = line.split('CREATE TABLE')[1].split('(')[0].strip().strip('"').strip("'")
                current_table = table_name
                current_columns = []
            elif line.startswith(')') or line.startswith(');'):
                # End of table definition
                if current_table and current_table in tables:
                    subset_schema_parts.append(f"CREATE TABLE {current_table} ({', '.join(current_columns)})")
                current_table = None
            elif current_table and current_table in tables:
                # Parse column definition
                if line and not line.startswith('--'):
                    # Extract column name (first word before space or comma)
                    col_name = line.split()[0].rstrip(',').strip('"').strip("'")
                    # Check if this column is in our identified columns or if we should include all columns for this table
                    # We include all columns for identified tables to be safe
                    current_columns.append(col_name)
        
        # Handle last table if needed
        if current_table and current_table in tables and current_columns:
            subset_schema_parts.append(f"CREATE TABLE {current_table} ({', '.join(current_columns)})")
        
        subset_schema = '\n'.join(subset_schema_parts) if subset_schema_parts else self.schema
        
        # Step 2: Generate SQL using only the linked subset
        sql_prompt = f"""Given the following database schema (which only contains the tables and columns relevant to the question) and the question, write the SQL query to answer the question.

Schema:
{subset_schema}

Question: {question}

Write a single SQL query that answers the question. Do not include any explanation, just the SQL query."""
        
        sql_response = self.llm(sql_prompt, system="", temperature=0.0, n=1)
        
        # Extract SQL from the response
        final_sql = bridge.extract_sql(sql_response)
        
        return final_sql