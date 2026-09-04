"""Schema-linking harness: first identify the tables/columns the question refers to, prune the schema to that linked subset in control flow, then generate SQL against the subset with bounded execution-based repair."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS1SchemaLink(SQLHarness):
    """Two-stage harness: (1) LLM-based schema linking finds the tables/columns
    mentioned in the question, (2) SQL is generated strictly against the linked
    schema subset, with a bounded execution-feedback repair loop."""

    LINK_SYSTEM = (
        "You are a schema-linking assistant for Text-to-SQL. Given a database "
        "schema and a natural-language question, identify exactly which tables "
        "and columns are needed to answer the question. Include columns needed "
        "for joins and filtering even if they are not explicitly named in the "
        "question. Respond with ONLY a JSON object of the form "
        '{"tables": ["table_a", "table_b"], "columns": ["table_a.col1", "col2"]}.'
    )

    SQL_SYSTEM = (
        "You are an expert SQLite query writer. You are given a LINKED SUBSET of "
        "a database schema: only the tables and columns relevant to the question. "
        "Write one valid SQLite query that answers the question using ONLY those "
        "linked tables and columns. Output ONLY the SQL query, no explanation, "
        "no markdown fences."
    )

    REPAIR_SYSTEM = (
        "You are an expert SQLite debugger. Fix the failing query using only the "
        "tables and columns present in the linked schema subset. Output ONLY the "
        "corrected SQL query, no explanation, no markdown fences."
    )

    # ------------------------------------------------------------------ #
    # Main control flow: link -> prune schema -> generate -> repair.     #
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        # Stage 1: schema linking -- which tables/columns does the question mention?
        links = self._link_schema(question)

        # Stage 2 (control flow, not prompt): prune the schema to the linked subset.
        linked_schema = self._filter_schema(self.schema, links)

        # Stage 3: write SQL against the linked subset only.
        sql = self._generate_sql(question, linked_schema, links)

        # Stage 4: bounded execution-feedback repair, still on the linked subset.
        for _ in range(3):
            if not sql:
                sql = self._generate_sql(question, linked_schema, links)
                continue
            result = self.execute(sql)
            if result.get("ok"):
                break
            sql = self._repair_sql(
                question, linked_schema, sql, result.get("error", "unknown error")
            )
        return sql

    # ------------------------------------------------------------------ #
    # Stage 1: schema linking.                                           #
    # ------------------------------------------------------------------ #
    def _link_schema(self, question: str) -> dict:
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Which tables and columns from the schema are needed to answer this "
            "question? Respond with the JSON object only."
        )
        response = self.llm(prompt, system=self.LINK_SYSTEM, temperature=0.0, n=1)
        links = self._parse_links(response)

        # Columns written as "table.column" also imply their table is linked.
        tables = list(links.get("tables", []))
        for col in links.get("columns", []):
            if "." in col:
                implied = col.split(".")[0].strip()
                if implied and implied not in tables:
                    tables.append(implied)
        links["tables"] = tables
        return links

    @staticmethod
    def _parse_links(text: str) -> dict:
        """Robustly extract {"tables": [...], "columns": [...]} from LLM output."""
        if not text:
            return {"tables": [], "columns": []}
        # Strip markdown code fences if present.
        cleaned = re.sub(r"