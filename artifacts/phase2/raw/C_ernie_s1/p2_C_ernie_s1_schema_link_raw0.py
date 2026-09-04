"""Harness that first uses LLM to identify relevant tables/columns from the question, then generates SQL against the linked schema subset."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS1SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Identify relevant tables and columns via LLM
        identify_prompt = f"""Given the following database schema:

{self.schema}

And the following question:

{question}

Identify which tables and columns are relevant to answering this question.
Return ONLY in the following format (no other text):
tables: table1, table2, ...
columns: table1.col1, table2.col2, ...
"""
        identification = self.llm(identify_prompt, system="", temperature=0.0, n=1)

        # Parse the identification result
        lines = identification.strip().split('\n')
        tables = []
        columns = []
        for line in lines:
            line_lower = line.lower().strip()
            if line_lower.startswith('tables:'):
                raw = line_lower.replace('tables:', '').strip()
                if raw:
                    tables = [t.strip() for t in raw.split(',')]
            elif line_lower.startswith('columns:'):
                raw = line_lower.replace('columns:', '').strip()
                if raw:
                    columns = [c.strip() for c in raw.split(',')]

        # Step 2: Build a linked subset schema containing only identified tables/columns
        # Parse original schema to extract table definitions
        schema_lines = self.schema.strip().split('\n')
        subset_schema_parts = []
        current_table = None
        for sline in schema_lines:
            sline = sline.strip()
            if not sline:
                continue
            # Detect table header (e.g., "Table name" or "table name")
            if sline.lower().startswith('table ') or sline.lower().startswith('table:'):
                table_name = sline.replace('Table', '').replace('table', '').replace(':', '').replace(' ', '').strip()
                if table_name in tables:
                    current_table = table_name
                    subset_schema_parts.append(f"Table {table_name}:")
                else:
                    current_table = None
            elif current_table and (':' in sline or sline.startswith('-') or sline.startswith('  ')):
                # This is a column definition line
                col_name = sline.split(':')[0].strip().lstrip('-').strip()
                full_col = f"{current_table}.{col_name}"
                if full_col in columns or col_name in [c.split('.')[-1] for c in columns if '.' in c]:
                    subset_schema_parts.append(f"  {col_name}")
            elif current_table and sline.lower().startswith('foreign key'):
                # Include foreign key info for the relevant table
                subset_schema_parts.append(f"  {sline}")

        subset_schema = '\n'.join(subset_schema_parts) if subset_schema_parts else self.schema

        # Step 3: Generate SQL against the linked subset schema
        sql_prompt = f"""Given the following relevant database schema (only tables and columns needed for the question):

{subset_schema}

And the following question:

{question}

Write a single SQL query that answers the question. Use the schema above.
Return ONLY the SQL query, no other text or explanation.
"""
        sql_text = self.llm(sql_prompt, system="", temperature=0.0, n=1)

        # Step 4: Extract and return the SQL
        final_sql = bridge.extract_sql(sql_text)
        return final_sql