"""Executes a two-step Text-to-SQL harness: first identifies relevant tables/columns via LLM, then generates SQL using only that subset."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Identify relevant tables and columns from the question
        identification_prompt = (
            f"Given the following database schema and question, identify the tables and columns "
            f"that are relevant to answering the question. Output ONLY in this exact format:\n"
            f"TABLES: [table1, table2, ...]\n"
            f"COLUMNS: [table1.col1, table2.col2, ...]\n\n"
            f"Schema: {self.schema}\n\n"
            f"Question: {question}"
        )
        identification_response = self.llm(
            identification_prompt,
            system="",
            temperature=0.0,
            n=1
        )
        
        # Parse the identification response
        lines = identification_response.strip().split('\n')
        tables = []
        columns = []
        for line in lines:
            if line.startswith("TABLES:"):
                tables_str = line.split(":", 1)[1].strip()
                if tables_str:
                    tables = [t.strip() for t in tables_str.split(',') if t.strip()]
            elif line.startswith("COLUMNS:"):
                cols_str = line.split(":", 1)[1].strip()
                if cols_str:
                    columns = [c.strip() for c in cols_str.split(',') if c.strip()]
        
        # Step 2: Generate SQL using only the identified tables and columns
        if not tables:
            # Fallback: use all tables if none identified
            tables = ["all_tables"]
            columns = ["all_columns"]
        
        subset_prompt = (
            f"Given the following database schema, write a SQL query to answer the question. "
            f"You MUST use ONLY the following tables and columns (do not use any others):\n"
            f"Tables: {tables}\n"
            f"Columns: {columns}\n\n"
            f"Schema: {self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write only the SQL query, nothing else."
        )
        
        sql_response = self.llm(
            subset_prompt,
            system="",
            temperature=0.0,
            n=1
        )
        
        final_sql = bridge.extract_sql(sql_response)
        return final_sql