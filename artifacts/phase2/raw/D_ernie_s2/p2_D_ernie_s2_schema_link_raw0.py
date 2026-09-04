"""This harness uses a two-step LLM call to first extract a relevant schema subset from the question and then generate SQL against that subset."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Identify relevant tables and columns by generating a simplified schema.
        schema_prompt = (
            f"Given the schema:\n{self.schema}\n\n"
            f"And the question: \"{question}\"\n\n"
            "Identify the tables and columns that are relevant to answer the question. "
            "Output a simplified schema that includes only those tables and their columns. "
            "Format as valid SQL CREATE TABLE statements."
        )
        simplified_schema = self.llm(schema_prompt, system="", temperature=0.0, n=1)
        
        # Step 2: Generate SQL using the simplified schema.
        sql_prompt = (
            f"Using the following simplified schema:\n{simplified_schema}\n\n"
            f"Write the SQL query to answer the question: \"{question}\". "
            "Output only the SQL query."
        )
        sql_text = self.llm(sql_prompt, system="", temperature=0.0, n=1)
        
        # Extract and return the SQL string.
        final_sql = bridge.extract_sql(sql_text)
        return final_sql