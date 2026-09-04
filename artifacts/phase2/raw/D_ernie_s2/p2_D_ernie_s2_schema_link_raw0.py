"""A harness that first identifies relevant tables/columns via LLM, then generates SQL against the reduced schema subset."""
from ..harness_base import SQLHarness
from .. import bridge
import re

class P2P2DErnieS2SchemaLink(SQLHarness):
    @staticmethod
    def _extract_tables_columns(text: str) -> dict:
        """Extract table and column names from LLM response using simple regex patterns."""
        tables = re.findall(r'table[s]?\s*[:\-]?\s*([\w_]+)', text, re.IGNORECASE)
        columns = re.findall(r'column[s]?\s*[:\-]?\s*([\w_]+)', text, re.IGNORECASE)
        return {"tables": list(set(tables)), "columns": list(set(columns))}

    def solve(self, question: str) -> str:
        # Step 1: Identify relevant tables and columns via LLM
        identify_prompt = f"""Given the following database schema and question, identify ONLY the tables and columns that are directly mentioned or implied by the question. 
Return your answer in this exact format:
Tables: table1, table2, ...
Columns: col1, col2, ...

Schema:
{self.schema}

Question: {question}

Identified:"""
        identify_response = self.llm(identify_prompt, system="", temperature=0.0, n=1)
        extracted = self._extract_tables_columns(identify_response)
        
        # Step 2: Build reduced schema subset containing only identified tables/columns
        # Parse the full schema to extract table definitions
        schema_lines = self.schema.strip().split('\n')
        reduced_schema_parts = []
        current_table = None
        
        for line in schema_lines:
            line = line.strip()
            if not line:
                continue
            # Detect table headers (common patterns: "CREATE TABLE", "Table:", etc.)
            if re.match(r'(CREATE\s+TABLE|Table\s*[:\-])\s+(\w+)', line, re.IGNORECASE):
                table_match = re.match(r'(CREATE\s+TABLE|Table\s*[:\-])\s+(\w+)', line, re.IGNORECASE)
                current_table = table_match.group(2)
                if current_table in extracted['tables']:
                    reduced_schema_parts.append(line)
            # Detect column definitions (common patterns: column_name type, etc.)
            elif current_table and re.match(r'(\w+)\s+', line):
                col_match = re.match(r'(\w+)\s+', line)
                if col_match.group(1) in extracted['columns']:
                    reduced_schema_parts.append(line)
            # Keep table definition lines if table is relevant
            elif current_table in extracted['tables']:
                reduced_schema_parts.append(line)
        
        reduced_schema = '\n'.join(reduced_schema_parts)
        if not reduced_schema.strip():
            # Fallback to full schema if no relevant parts found
            reduced_schema = self.schema
        
        # Step 3: Generate SQL using the reduced schema subset
        sql_prompt = f"""Given the following database schema (ONLY the relevant subset) and question, write a single SQL query to answer the question.

Schema:
{reduced_schema}

Question: {question}

SQL Query:"""
        sql_response = self.llm(sql_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(sql_response)
        
        return final_sql