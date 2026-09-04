"""A Text-to-SQL harness that first identifies relevant tables/columns via LLM, then generates SQL against a schema subset."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS1SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Identify relevant tables/columns using LLM
        identify_prompt = f"""Given the question: "{question}" and the database schema:
{self.schema}

List all tables and columns that are relevant to answering this question. 
Return in JSON format: {{"tables": ["table1", "table2"], "columns": ["table1.col1", "table2.col2"]}}
Only include tables/columns that are explicitly mentioned or logically required."""
        
        identification = self.llm(identify_prompt, system="", temperature=0.0, n=1)
        
        # Parse the identification result (simple extraction, assuming valid JSON)
        import json
        try:
            # Try to extract JSON from the response
            start = identification.find('{')
            end = identification.rfind('}') + 1
            if start != -1 and end > start:
                relevant = json.loads(identification[start:end])
            else:
                # Fallback: assume the response is already JSON
                relevant = json.loads(identification)
        except json.JSONDecodeError:
            # If parsing fails, use empty lists (will fall back to full schema)
            relevant = {"tables": [], "columns": []}
        
        # Step 2: Create linked subset schema
        if relevant["tables"]:
            # Extract table definitions from full schema
            table_defs = []
            schema_lines = self.schema.strip().split('\n')
            current_table = None
            for line in schema_lines:
                line = line.strip()
                if line.upper().startswith('CREATE TABLE'):
                    current_table = line.split()[2].strip('`"')
                elif current_table and line.upper().startswith(')'):
                    current_table = None
                elif current_table and current_table in relevant["tables"]:
                    table_defs.append(line)
            
            if table_defs:
                subset_schema = '\n'.join(table_defs)
            else:
                subset_schema = self.schema
        else:
            subset_schema = self.schema
        
        # Step 3: Generate SQL using the subset schema
        sql_prompt = f"""Given the question: "{question}" and the database schema:
{subset_schema}

Write a SQL query to answer the question. Use only the tables and columns provided in the schema.
Return only the SQL query, nothing else."""
        
        sql_response = self.llm(sql_prompt, system="", temperature=0.0, n=1)
        
        # Step 4: Extract SQL from response
        final_sql = bridge.extract_sql(sql_response)
        
        return final_sql