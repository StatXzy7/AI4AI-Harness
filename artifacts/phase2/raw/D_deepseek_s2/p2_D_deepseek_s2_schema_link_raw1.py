"""First performs LLM schema linking to identify relevant tables/columns, then writes SQL using only that linked schema subset."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: schema linking
        linking_prompt = (
            "You are a database schema linker for Text-to-SQL.\n"
            "Given the user question and the database schema, identify all tables and columns that are needed "
            "to write the SQL query. Include columns that are directly mentioned or clearly required for joins, "
            "filters, grouping, and the SELECT clause.\n\n"
            "Return a JSON object with the following structure:\n"
            '{"tables": [{"table": "table_name", "columns": ["col1", "col2"]}]}\n\n'
            f"Question:\n{question}\n\n"
            f"Schema:\n{self.schema}\n\n"
            "Return only JSON."
        )
        link_resp = self._call_llm(linking_prompt, "You return only valid JSON schema links.")
        links = self._parse_links(link_resp)

        # Step 2: build linked schema subset
        linked_schema = self._build_linked_schema(links) if links else self.schema

        # Step 3: generate SQL against the linked subset
        sql = self._generate_sql(question, linked_schema)
        if not sql:
            sql = self._generate_sql(question, self.schema)

        # Optional lightweight validation and repair
        if sql and self._is_query(sql):
            try:
                result = self.execute(sql)
            except Exception:
                return sql

            if result.get("ok"):
                return sql

            error = result.get("error") or "unknown execution error"
            repaired = self._repair_sql(question, sql, error)
            if repaired:
                if self._is_query(repaired):
                    try:
                        if self.execute(repaired).get("ok"):
                            return repaired
                    except Exception:
                        pass
                return repaired

        return sql or ""

    def _call_llm(self, prompt: str, system: str) -> str:
        try:
            resp = self.llm(prompt, system=system, temperature=0.0, n=1)
        except TypeError:
            resp = self.llm(prompt)

        if isinstance(resp, (list, tuple)):
            resp = resp[0] if resp else ""
        if resp is None:
            return ""
        return str(resp)

    def _parse_links(self, text: str):
        if not text:
            return None

        cleaned = text.strip()
        cleaned = re.sub(r"