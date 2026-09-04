"""This harness first uses an LLM to identify tables and columns mentioned in the question, then generates SQL against a filtered schema subset."""

from ..harness_base import SQLHarness
from .. import bridge
import json


class P2P2DErnieS0SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Identify tables and columns from the question
        identify_prompt = (
            f"Extract all table names and column names mentioned in the following question. "
            f"Return a JSON object with keys 'tables' (list of table names) and 'columns' (list of column names). "
            f"Question: {question}"
        )
        identify_response = self.llm(identify_prompt, system="", temperature=0.0, n=1)
        try:
            identify_data = json.loads(identify_response)
            tables = identify_data.get("tables", [])
            columns = identify_data.get("columns", [])
        except json.JSONDecodeError:
            tables = []
            columns = []

        # Step 2: Create a subset schema from self.schema that includes only the identified tables
        schema_lines = self.schema.split(";")
        subset_lines = []
        for line in schema_lines:
            line = line.strip()
            if line.startswith("CREATE TABLE"):
                parts = line.split()
                if len(parts) >= 3:
                    table_name = parts[2]
                    if table_name in tables:
                        subset_lines.append(line)
        if not subset_lines:
            subset_schema = self.schema
        else:
            subset_schema = "; ".join(subset_lines) + ";"

        # Step 3: Generate SQL using the subset schema
        sql_prompt = (
            f"Given the following database schema (only the mentioned tables and their columns):\n\n"
            f"{subset_schema}\n\n"
            f"Write a SQL query to answer the question: {question}\n"
            f"Return only the SQL query, no other text."
        )
        sql_response = self.llm(sql_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(sql_response)
        return final_sql