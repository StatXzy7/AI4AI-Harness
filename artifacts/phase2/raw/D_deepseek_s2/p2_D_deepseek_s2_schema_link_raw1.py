"""Two-stage Text-to-SQL harness that first links question terms to schema tables/columns and then generates SQL using only that linked schema subset."""
import json
import re
from typing import Any, Dict, List

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: identify relevant tables/columns mentioned in the question.
        linked_tables = self._link_schema(question)
        linked_schema = self._format_linked_schema(linked_tables)

        # Stage 2: generate SQL against only the linked subset.
        raw_sql = self._generate_sql(question, linked_schema)
        sql = bridge.extract_sql(raw_sql)
        return sql or raw_sql.strip()

    def _link_schema(self, question: str) -> List[Dict[str, Any]]:
        system = (
            "You are an expert database schema linker. Identify only the tables and columns "
            "that are mentioned or necessarily implied by the user's question. "
            'Return a single JSON object in the form {"tables":[{"name":"table_name","columns":["col1","col2"]}]}.'
        )
        prompt = f"""Database schema:
{self.schema}

Question:
{question}

Return only the JSON object, with no additional commentary."""
        response = self._call_llm(prompt, system)
        data = self._parse_json(response)

        if not isinstance(data, dict):
            return []
        tables = data.get("tables", [])
        if not isinstance(tables, list):
            return []
        return [t for t in tables if isinstance(t, dict)]

    def _generate_sql(self, question: str, linked_schema: str) -> str:
        system = (
            "You are an expert SQLite SQL writer. Write a single SQL query that answers "
            "the user's question using only the provided linked schema subset. "
            "Do not use tables or columns that are not explicitly listed below."
        )
        prompt = f"""Linked schema subset (only these tables/columns are relevant):
{linked_schema}

Question:
{question}

Return only SQLite SQL, with no explanation or markdown fences."""
        return self._call_llm(prompt, system)

    def _call_llm(self, prompt: str, system: str = "") -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        return self._unwrap_completion(response)

    @staticmethod
    def _unwrap_completion(response: Any) -> str:
        if isinstance(response, str):
            return response

        if isinstance(response, list):
            for item in response:
                if isinstance(item, str):
                    return item
                if isinstance(item, dict):
                    text = (
                        item.get("text")
                        or item.get("content")
                        or item.get("message", {}).get("content")
                        if isinstance(item.get("message", {}), dict)
                        else None
                    )
                    if text:
                        return str(text)
            return ""

        if isinstance(response, dict):
            for key in ("text", "content"):
                if response.get(key):
                    return str(response[key])

            choices = response.get("choices", [])
            if isinstance(choices, list):
                for choice in choices:
                    if isinstance(choice, str):
                        return choice
                    if isinstance(choice, dict):
                        text = (
                            choice.get("text")
                            or choice.get("content")
                            or choice.get("message", {}).get("content")
                            if isinstance(choice.get("message", {}), dict)
                            else None
                        )
                        if text:
                            return str(text)

            message = response.get("message")
            if isinstance(message, str):
                return message
            if isinstance(message, dict):
                return str(message.get("content", ""))

        return str(response)

    @staticmethod
    def _parse_json(text: str) -> Any:
        if not text:
            return None

        cleaned = text.strip()
        # Remove common code fences.
        cleaned = re.sub(r"