"""Schema-link the question to relevant tables/columns first, then generate the SQL query against only that linked subset."""
import json
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS0SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: identify tables/columns mentioned in the question.
        linking_prompt = (
            "Given a database schema and a natural language question, identify only the "
            "tables and columns that are mentioned or needed to answer the question.\n"
            "Return a JSON object with two keys:\n"
            '  "tables": list of relevant table names\n'
            '  "columns": list of relevant fully-qualified column names, e.g. "table.column"\n\n'
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return only JSON, no explanation."
        )
        linking_output = self._llm_text(
            self.llm(
                linking_prompt,
                system="You are a precise schema linker for Text-to-SQL.",
                temperature=0.0,
                n=1,
            )
        )
        linked = self._parse_linking(linking_output)
        linked_block = self._format_linked(linked, linking_output)

        # Stage 2: write SQL against the linked subset.
        sql_prompt = (
            "Write a SQLite SQL query to answer the question.\n"
            "Use only the tables and columns in the linked subset below. "
            "Do not introduce any table or column outside the linked subset.\n\n"
            f"Full schema for reference:\n{self.schema}\n\n"
            f"Linked subset:\n{linked_block}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL query, no explanation."
        )
        sql_output = self._llm_text(
            self.llm(
                sql_prompt,
                system="You are a careful SQL writer.",
                temperature=0.0,
                n=1,
            )
        )
        sql = bridge.extract_sql(sql_output)
        if not sql:
            sql = sql_output.strip()
        return sql

    @staticmethod
    def _llm_text(output):
        """Normalize an LLM return value to a string."""
        if isinstance(output, list):
            return output[0] if output else ""
        return output or ""

    @staticmethod
    def _parse_linking(text: str) -> dict:
        """Parse the linker JSON output into tables and columns."""
        if not text:
            return {"tables": [], "columns": []}

        cleaned = text.strip()
        # Remove Markdown code fences if present.
        cleaned = re.sub(r"^