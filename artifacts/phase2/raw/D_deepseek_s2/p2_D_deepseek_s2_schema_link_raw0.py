"""Two-stage harness that first identifies relevant schema tables/columns from the question and then writes SQL against only that linked schema subset."""

import json
import re
from typing import List, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: link the question to schema tables and columns.
        linked_tables, linked_columns = self._link_schema(question)

        # Build a filtered schema subset containing only linked tables.
        linked_subset = self._filter_schema(linked_tables)

        # Step 2: generate SQL against the linked subset.
        return self._generate_sql(question, linked_subset, linked_tables, linked_columns)

    def _link_schema(self, question: str) -> Tuple[List[str], List[str]]:
        link_system = (
            "You are a schema linking expert. Given a database schema and a question, "
            "identify the tables and columns that are relevant. Return only JSON."
        )
        prompt = f"""Database schema:
{self.schema}

Question:
{question}

Return a JSON object with exactly two keys:
{{
  "tables": ["TableName", ...],
  "columns": ["TableName.ColumnName", ...]
}}
Only include tables and columns mentioned or clearly needed by the question."""

        raw = self.llm(prompt, system=link_system, temperature=0.0, n=1)
        return self._parse_link_output(raw, question)

    def _parse_link_output(self, raw, question: str) -> Tuple[List[str], List[str]]:
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        raw = raw or ""
        raw = raw.strip()
        if not raw:
            return self._fallback_link(question)

        raw_clean = re.sub(r"^