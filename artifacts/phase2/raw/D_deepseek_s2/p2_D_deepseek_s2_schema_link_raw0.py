"""Identify relevant tables/columns via an LLM schema-linking pass, then generate SQL using only the linked subset."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2SchemaLink(SQLHarness):
    """Text-to-SQL harness that links schema elements before SQL generation."""

    def solve(self, question: str) -> str:
        # Step 1: Schema linking
        linking_prompt = f"""You are an expert database schema linker for Text-to-SQL.

Database schema:
{self.schema}

Question:
{question}

Identify the minimal set of tables and columns needed to answer the question, including columns required for joins, filters, and aggregations. Do not invent table or column names.

Return only JSON in the following format:
{{
  "tables": [
    {{"table": "table_name", "columns": ["column1", "column2"]}}
  ]
}}"""

        linking_response = self._call_llm(linking_prompt)
        linked_data = self._extract_json(linking_response)
        linked_schema = self._build_linked_schema(linked_data, self.schema)

        # Step 2: Write SQL against the linked subset
        sql_prompt = f"""You are an expert SQL writer. Write a single SQLite query for the question using only the linked schema subset below.

Linked schema subset:
{linked_schema}

Question:
{question}

Return only SQL, with no explanation or Markdown fences."""

        sql_response = self._call_llm(sql_prompt)
        final_sql = bridge.extract_sql(sql_response)
        if not final_sql:
            final_sql = self._fallback_extract_sql(sql_response)
        return final_sql

    def _call_llm(self, prompt: str) -> str:
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            if response.get("text"):
                return response["text"]
            if response.get("completion"):
                return response["completion"]
            choices = response.get("choices")
            if choices and isinstance(choices, list):
                first = choices[0]
                if isinstance(first, dict):
                    text = first.get("text")
                    if text:
                        return text
                    message = first.get("message")
                    if isinstance(message, dict):
                        return message.get("content", "")
        if hasattr(response, "text"):
            return response.text
        if hasattr(response, "content"):
            return response.content
        return str(response)

    @staticmethod
    def _extract_json(text: str):
        if not isinstance(text, str):
            return None
        text = text.strip()
        # Remove code fences if present.
        text = re.sub(r"