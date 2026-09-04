"""A Text-to-SQL harness that first identifies relevant tables/columns from the question and then writes SQL against the linked schema subset."""
import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS0SchemaLink(SQLHarness):
    """Schema-link first, then generate SQL using only the linked subset."""

    def solve(self, question: str) -> str:
        tables, columns = self._link_schema(question)
        linked_schema = self._build_linked_schema(tables, columns)
        return self._generate_sql(question, linked_schema)

    def _link_schema(self, question: str):
        prompt = f"""You are given a database schema and a natural-language question.
Perform schema linking: identify the exact tables and columns that are relevant for writing the SQL query.

Database schema:
{self.schema}

Question:
{question}

Return a JSON object with the exact schema names only:
{{"tables": ["table_name"], "columns": ["column_name"]}}
Do not include any other text.
"""
        raw = self.llm(prompt, system="You are a careful database schema linker.", temperature=0.0, n=1)
        if not isinstance(raw, str):
            raw = str(raw)

        parsed = self._parse_json(raw)
        tables = parsed.get("tables", []) if isinstance(parsed, dict) else []
        columns = parsed.get("columns", []) if isinstance(parsed, dict) else []

        tables = [t for t in tables if isinstance(t, str)]
        columns = [c for c in columns if isinstance(c, str)]
        return tables, columns

    def _parse_json(self, text: str):
        text = text.strip()
        text = re.sub(r"