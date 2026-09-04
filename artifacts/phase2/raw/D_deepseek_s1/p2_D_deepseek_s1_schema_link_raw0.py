"""This harness first performs schema linking to identify the relevant tables and columns in the question, then writes SQL against the linked subset."""
import json

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS1SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        linking_response = self.llm(
            self._schema_linking_prompt(question),
            system="You are a schema linking expert. Return only JSON.",
            temperature=0.0,
            n=1,
        )
        linked_schema = self._build_linked_schema(linking_response)

        sql_response = self.llm(
            self._sql_generation_prompt(question, linked_schema),
            system="You are an expert SQL query generator. Return only SQL.",
            temperature=0.0,
            n=1,
        )

        if isinstance(sql_response, list):
            sql_response = sql_response[0] if sql_response else ""
        return bridge.extract_sql(sql_response)

    def _schema_linking_prompt(self, question: str) -> str:
        return (
            "Question: " + question + "\n\n"
            "Database schema:\n" + self.schema + "\n\n"
            "Identify only the tables and columns that are relevant to answer the question. "
            "Output a JSON array of objects in the exact format:\n"
            '[\n  {"table": "<table_name>", "columns": ["<column_name>", ...]},\n  ...\n]\n'
            "Do not include irrelevant tables or columns. Do not include any text outside JSON."
        )

    def _sql_generation_prompt(self, question: str, linked_schema: str) -> str:
        return (
            "Database schema (only relevant tables and columns):\n" + linked_schema + "\n\n"
            "Question: " + question + "\n\n"
            "Write a single SQL query to answer the question. Use only the tables and columns listed above. "
            "Return only the SQL query without any explanation."
        )

    def _build_linked_schema(self, response) -> str:
        if isinstance(response, list):
            response = response[0] if response else ""
        if not isinstance(response, str):
            return self.schema

        parsed = self._parse_linking_json(response)
        if parsed is None:
            return self.schema

        formatted = self._format_linked_objects(parsed)
        return formatted if formatted else self.schema

    def _parse_linking_json(self, text: str):
        text = text.strip()
        if text.startswith("