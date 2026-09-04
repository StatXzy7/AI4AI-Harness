"""First performs schema linking to identify relevant tables and columns, then generates SQL using only the linked subset."""
import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        linked_schema = self._link_schema(question)
        sql = self._generate_sql(question, linked_schema)
        return sql

    def _call_llm(self, prompt: str, system: str = "") -> str:
        result = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(result, list):
            return result[0] if result else ""
        if isinstance(result, dict):
            for key in ("text", "content", "completion", "message"):
                if key in result:
                    value = result[key]
                    if isinstance(value, list):
                        return value[0] if value else ""
                    return str(value)
        return str(result)

    def _link_schema(self, question: str) -> str:
        system = (
            "You are a precise database schema linker. "
            "Given a database schema and a natural-language question, identify only the tables and columns "
            "that are necessary to answer the question. Do not include irrelevant tables or columns."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            'Return a JSON object with the following structure:\n'
            '{"tables": [{"name": "table_name", "columns": ["col1", "col2"]}]}\n'
            'Include only columns that are explicitly needed or highly likely to be needed.'
        )
        raw = self._call_llm(prompt, system)
        linked = self._parse_json(raw)
        if linked is None:
            return self.schema
        return self._format_linked_schema(linked)

    def _generate_sql(self, question: str, linked_schema: str) -> str:
        system = (
            "You are an expert SQL writer. "
            "Write a correct SQLite query for the given question using only the linked schema provided."
        )
        prompt = (
            "Linked schema:\n"
            f"{linked_schema}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL query, without markdown fences or extra explanation."
        )
        raw = self._call_llm(prompt, system)
        sql = bridge.extract_sql(raw)
        if not sql:
            sql = raw.strip()
        return sql

    def _parse_json(self, text: str):
        if not text:
            return None

        cleaned = text.strip()
        if cleaned.startswith("