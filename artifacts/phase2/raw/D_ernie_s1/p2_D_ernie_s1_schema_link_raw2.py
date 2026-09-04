"""A harness that first identifies relevant tables/columns from the question, then generates SQL using only that schema subset."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS1SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Identify relevant tables and columns using the LLM
        identify_prompt = f"""Given the following database schema and question, identify which tables and columns are relevant.
Output ONLY a comma-separated list of table names, then a comma-separated list of column names (with table prefixes like 'table.column').

Schema:
{self.schema}

Question: {question}

Tables:"""
        
        identify_response = self.llm(identify_prompt, system="", temperature=0.0, n=1)
        
        # Parse the identification response
        tables = []
        columns = []
        lines = identify_response.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('Tables:'):
                tables = [t.strip() for t in line.split(':', 1)[1].split(',') if t.strip()]
            elif line.startswith('Columns:'):
                columns = [c.strip() for c in line.split(':', 1)[1].split(',') if c.strip()]
        
        # If no tables identified, fallback to all tables
        if not tables:
            # Extract all table names from schema (assuming CREATE TABLE format)
            import re
            tables = re.findall(r'CREATE TABLE\s+(\w+)', self.schema, re.IGNORECASE)
        
        # Step 2: Build subset schema containing only identified tables and their columns
        subset_schema_parts = []
        
        # Parse original schema to extract table definitions
        # Assuming standard SQL CREATE TABLE format
        import re
        table_pattern = re.compile(
            r'CREATE TABLE\s+(\w+)\s*\((.*?)\)\s*;',
            re.IGNORECASE | re.DOTALL
        )
        
        for match in table_pattern.finditer(self.schema):
            table_name = match.group(1)
            if table_name in tables:
                # Extract column definitions for this table
                table_def = match.group(0)
                # Filter columns if we have identified specific ones
                if columns:
                    # Keep only columns that are in the identified list for this table
                    col_pattern = re.compile(r'(\w+)\s+', re.IGNORECASE)
                    col_names = col_pattern.findall(match.group(2))
                    filtered_cols = [col for col in col_names if f'{table_name}.{col}' in columns]
                    if filtered_cols:
                        # Rebuild the table definition with only relevant columns
                        # This is a simplified approach - in practice might need more robust parsing
                        new_def = f"CREATE TABLE {table_name} (\n"
                        for col in filtered_cols:
                            # Find the original column line
                            for line in match.group(2).split('\n'):
                                if line.strip().startswith(col):
                                    new_def += f"  {line.strip()},\n"
                        new_def = new_def.rstrip(',\n') + "\n);"
                        subset_schema_parts.append(new_def)
                else:
                    subset_schema_parts.append(table_def)
        
        # If we couldn't parse any tables, use the original schema
        if not subset_schema_parts:
            subset_schema = self.schema
        else:
            subset_schema = '\n\n'.join(subset_schema_parts)
        
        # Step 3: Generate SQL using only the subset schema
        generate_prompt = f"""Given the following database schema (containing only relevant tables/columns) and question, write the SQL query.

Schema:
{subset_schema}

Question: {question}

Write the SQL query that answers the question. Output ONLY the SQL query."""
        
        generate_response = self.llm(generate_prompt, system="", temperature=0.0, n=1)
        
        # Extract SQL from the response
        final_sql = bridge.extract_sql(generate_response)
        
        return final_sql