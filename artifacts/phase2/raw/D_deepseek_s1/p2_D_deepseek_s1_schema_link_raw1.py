"""Two-stage schema linking followed by SQL generation against only the linked subset."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS1SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: identify tables and columns relevant to the question.
        schema_linking_prompt = (
            "You are given a database schema and a natural language question.\n"
            "Identify only the tables and columns that are necessary to answer the question.\n"
            "Return a compact schema subset. Copy the table and column definitions verbatim "
            "from the input schema; do not add, rename, or modify any definitions.\n"
            "Include only the relevant tables and columns. If no filtering is needed, return "
            "the complete schema.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Relevant schema subset:"
        )
        linked_subset = self._call_llm(
            schema_linking_prompt,
            system="You are an expert database schema linker.",
        ).strip()

        if not linked_subset:
            linked_subset = self.schema

        # Stage 2: write SQL against the linked subset.
        sql_generation_prompt = (
            "Write a SQL query that answers the question using only the provided schema subset.\n"
            "Return only the SQL query, with no explanation.\n\n"
            f"Schema subset:\n{linked_subset}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        sql_text = self._call_llm(
            sql_generation_prompt,
            system="You are an expert SQL writer. Generate only SQL.",
        )

        return bridge.extract_sql(sql_text)

    def _call_llm(self, prompt: str, system: str) -> str:
        result = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(result, list):
            return str(result[0]) if result else ""
        return str(result or "")