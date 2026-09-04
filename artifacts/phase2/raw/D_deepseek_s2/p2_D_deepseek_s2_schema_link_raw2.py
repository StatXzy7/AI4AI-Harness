"""Two-phase schema linking: first identify relevant tables and columns, then generate SQL against only the linked schema subset."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Phase 1: identify mentioned/necessary tables and columns.
        link_prompt = self._build_link_prompt(question)
        link_response = self.llm(link_prompt)
        links = self._parse_links(link_response)

        # Build the linked schema subset used by the SQL generation phase.
        linked_schema = self._build_linked_schema(links)

        # Phase 2: generate SQL using only the linked subset.
        sql_prompt = self._build_sql_prompt(question, linked_schema)
        sql_response = self.llm(sql_prompt)

        sql = bridge.extract_sql(sql_response)
        if not sql:
            sql = self._fallback_extract_sql(sql_response)

        return sql.strip()

    def _build_link_prompt(self, question: str) -> str:
        return (
            "You are a schema linker for Text-to-SQL. Given a database schema and a natural-language question, "
            "identify the tables and columns that are mentioned in the question or clearly necessary for joins, filters, grouping, or selection.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return a JSON object whose keys are relevant table names and whose values are arrays of relevant column names. "
            "Return only JSON. Example: {\"users\": [\"id\", \"name\"], \"orders\": [\"user_id\"]}"
        )

    def _parse_links(self, raw: str) -> dict:
        text = raw.strip()
        # Remove markdown code fences if present.
        text = re.sub(r'