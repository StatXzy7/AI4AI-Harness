"""Identifies mentioned tables/columns in the question, then generates SQL against only those schema elements using a frozen LLM."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS1SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Parse schema into table->columns mapping
        schema_dict = {}
        for stmt in self.schema.split(';'):
            stmt = stmt.strip()
            if not stmt or 'CREATE TABLE' not in stmt:
                continue
            # Extract table name
            table_part = stmt.split('CREATE TABLE')[1].strip()
            table_name = table_part.split('(')[0].strip()
            # Extract columns
            cols_part = table_part.split('(')[1].rstrip(')').strip()
            columns = [col.strip().split()[0] for col in cols_part.split(',') if col.strip()]
            schema_dict[table_name] = columns

        # Identify mentioned tables and columns (case-insensitive)
        question_lower = question.lower()
        mentioned_tables = set()
        mentioned_columns = set()
        
        for table, cols in schema_dict.items():
            if table.lower() in question_lower:
                mentioned_tables.add(table)
                # Add all columns of mentioned tables (needed for joins/context)
                mentioned_columns.update(cols)
            else:
                # Check individual columns
                for col in cols:
                    if col.lower() in question_lower:
                        mentioned_tables.add(table)
                        mentioned_columns.add(col)

        # Build linked schema subset
        linked_schema_parts = []
        for table in mentioned_tables:
            cols = schema_dict[table]
            # Include only mentioned columns for this table, but keep table structure
            mentioned_cols_for_table = [c for c in cols if c in mentioned_columns]
            if mentioned_cols_for_table:
                cols_str = ', '.join(f"{c} TEXT" for c in mentioned_cols_for_table)
                linked_schema_parts.append(f"CREATE TABLE {table} ({cols_str});")
        
        linked_schema = '\n'.join(linked_schema_parts) if linked_schema_parts else "No tables mentioned."

        # Generate prompt with linked schema only
        prompt = f"""Schema:
{linked_schema}

Question: {question}

SQL:"""
        
        # Call frozen LLM (temperature=0, single sample)
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        
        # Extract SQL from response
        sql = bridge.extract_sql(response)
        
        # Return the generated SQL string
        return sql