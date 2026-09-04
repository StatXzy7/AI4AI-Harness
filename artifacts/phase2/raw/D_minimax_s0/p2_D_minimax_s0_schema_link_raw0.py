"""Schema-linking harness that first extracts referenced tables/columns from the natural language question, then writes SQL restricted to that subset."""
from __future__ import annotations

import json
import re
from typing import List, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS0SchemaLink(SQLHarness):
    """Two-pass harness: (1) identify tables/columns referenced by the question,
    (2) generate SQL using only the linked schema subset."""

    # ------------------------------------------------------------------ #
    # Prompt fragments
    # ------------------------------------------------------------------ #
    LINKER_SYSTEM = (
        "You are a precise schema-linker. Given a database schema (a list of "
        "CREATE TABLE statements) and a natural language question, identify the "
        "minimal set of tables and columns required to answer the question. "
        "Respond with a JSON object of the form "
        '{"tables": ["table1", "table2", ...], "columns": ["table1.col1", ...]}. '
        "Do not output any explanation."
    )

    SQL_SYSTEM = (
        "You are an expert SQL writer. Given a question and a pruned database "
        "schema, produce a single SQLite-compatible SQL query that answers it. "
        "Return ONLY the SQL -- no prose, no markdown fences."
    )

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        # ---------- Pass 1: schema linking ------------------------------ #
        linked_tables, linked_columns = self._schema_link(question)

        # Build a pruned schema containing only the linked subset. If the
        # linker returned nothing useful, fall back to the full schema so the
        # SQL-writing stage still has something to work with.
        pruned_schema = self._prune_schema(linked_tables, linked_columns)
        schema_for_sql = pruned_schema if pruned_schema.strip() else self.schema

        # ---------- Pass 2: SQL generation against linked schema ------- #
        sql_prompt = (
            f"Question: {question.strip()}\n\n"
            f"Relevant schema:\n{schema_for_sql}\n\n"
            "SQL:"
        )
        raw = self.llm(sql_prompt, system=self.SQL_SYSTEM, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        # ---------- Light self-correction on syntax errors -------------- #
        if sql:
            verdict = self.execute(sql)
            if not verdict.get("ok") and verdict.get("error"):
                sql = self._correct(question, schema_for_sql, sql, verdict["error"])

        return sql or ""

    # ------------------------------------------------------------------ #
    # Pass 1: schema linking
    # ------------------------------------------------------------------ #
    def _schema_link(self, question: str) -> Tuple[List[str], List[str]]:
        """Ask the LLM which tables/columns the question refers to."""
        prompt = (
            f"Full schema:\n{self.schema}\n\n"
            f"Question: {question.strip()}\n\n"
            "Linked tables/columns (JSON):"
        )
        raw = self.llm(prompt, system=self.LINKER_SYSTEM, temperature=0.0, n=1)

        tables: List[str] = []
        columns: List[str] = []

        # Try a strict JSON parse first; fall back to permissive extraction.
        data = self._safe_json(raw)
        if isinstance(data, dict):
            tables = [t for t in data.get("tables", []) if isinstance(t, str)]
            columns = [c for c in data.get("columns", []) if isinstance(c, str)]
        else:
            tables, columns = self._regex_link_extract(raw)

        # Normalise: strip whitespace, lower-case tables for matching.
        tables = [t.strip().strip("`\"[]") for t in tables if t.strip()]
        columns = [c.strip().strip("`\"[]") for c in columns if c.strip()]

        # Final defensive net: regex-search the original question against the
        # schema strings themselves so we never return an empty link.
        if not tables and not columns:
            tables, columns = self._regex_link_against_schema(question)

        return tables, columns

    @staticmethod
    def _safe_json(text: str):
        """Best-effort JSON load; returns None if impossible."""
        if not text:
            return None
        # Strip code fences if present.
        cleaned = re.sub(r"