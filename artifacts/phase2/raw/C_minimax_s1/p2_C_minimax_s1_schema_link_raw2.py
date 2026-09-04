"""Wraps a frozen text-to-SQL solver by first performing schema linking to identify relevant tables and columns, then generating SQL against the reduced schema subset."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS1SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Schema linking - identify tables and columns mentioned in the question
        linking_prompt = (
            "You are a schema linking assistant. Given a database schema and a natural language "
            "question, identify ONLY the tables and columns that are relevant to answering the "
            "question.\n\n"
            f"Database Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Output the relevant tables and columns in a concise list format. "
            "List each table name on its own line, followed by its relevant column names. "
            "Do not output any SQL or explanations, only the linked schema subset."
        )

        linking_response = self.llm(linking_prompt, system="", temperature=0.0, n=1)
        linked_schema = linking_response.strip()

        # Step 2: Generate SQL using only the linked schema subset
        sql_prompt = (
            "You are an expert SQL generator. Given a natural language question and a relevant "
            "schema subset (already filtered to only the tables and columns needed), write the "
            "SQL query that answers the question.\n\n"
            f"Relevant Schema:\n{linked_schema}\n\n"
            f"Full Schema (for reference):\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write ONLY the SQL query. Do not include explanations, markdown formatting, "
            "or any text other than the SQL itself."
        )

        sql_response = self.llm(sql_prompt, system="", temperature=0.0, n=1)
        sql_candidate = bridge.extract_sql(sql_response)

        # Step 3: Validate by attempting execution; on failure, retry with full schema
        result = self.execute(sql_candidate)
        if not result["ok"]:
            fallback_prompt = (
                "You are an expert SQL generator. Given a natural language question and the "
                "full database schema, write the SQL query that answers the question.\n\n"
                f"Database Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"The previous attempt failed with error: {result['error']}\n\n"
                "Write ONLY the corrected SQL query."
            )
            fallback_response = self.llm(fallback_prompt, system="", temperature=0.0, n=1)
            sql_candidate = bridge.extract_sql(fallback_response)

        return sql_candidate