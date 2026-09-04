"""Two-stage harness: an LLM schema-linking pass prunes the schema to the question-relevant tables/columns, then SQL is written and execution-repaired against that linked subset."""

from __future__ import annotations

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2SchemaLink(SQLHarness):
    """Schema-link-then-write Text-to-SQL harness around a frozen weak solver.

    Control flow (the strategy is enforced here, not merely prompted):
      1. LINK   -- ask the frozen LLM which tables/columns of ``self.schema``
                   the question needs, parse the answer, and physically prune
                   the schema text down to the linked tables.
      2. WRITE  -- ask the frozen LLM for SQL using ONLY the linked schema
                   subset plus the linked-column hints.
      3. REPAIR -- execute the candidate SQL; on failure, feed the database
                   error back and let the LLM fix it (bounded attempts).
    """

    MAX_REPAIR_ATTEMPTS = 2

    _CREATE_TABLE_RE = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?:[\"'`\[]([^\"'`\]]+)[\"'`\]]|([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?))",
        re.IGNORECASE,
    )

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        preamble, schema_parts = self._split_schema(self.schema)

        # ---- Stage 1: schema linking (table + column selection) --------
        linked_tables, linked_columns = self._link_schema(question, schema_parts)
        linked_schema = self._render_linked_schema(preamble, schema_parts, linked_tables)

        # ---- Stage 2: SQL generation against the linked subset ---------
        sql = self._generate_sql(question, linked_schema, linked_columns)

        # ---- Stage 3: bounded execution-feedback repair loop -----------
        total_attempts = 1 + self.MAX_REPAIR_ATTEMPTS
        for attempt in range(total_attempts):
            try:
                result = self.execute(sql)
            except Exception as exc:  # defensive: treat executor crashes as errors
                result = {"ok": False, "error": str(exc)}
            if result.get("ok"):
                return sql
            if attempt + 1 < total_attempts:
                sql = self._repair_sql(
                    question,
                    linked_schema,
                    sql,
                    result.get("error", "") or "unknown execution error",
                )
        return sql

    # ------------------------------------------------------------------ #
    # LLM plumbing
    # ------------------------------------------------------------------ #
    def _ask(self, prompt: str, system: str = "") -> str:
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    # ------------------------------------------------------------------ #
    # Stage 1 helpers: schema splitting and linking
    # ------------------------------------------------------------------ #
    def _split_schema(self, schema: str):
        """Split the DDL into (preamble, parts).

        ``parts`` maps lowercased table name -> (original name, DDL chunk),
        preserving the order in which tables appear in the schema.
        """
        schema = schema or ""
        matches = list(self._CREATE_TABLE_RE.finditer(schema))
        if not matches:
            return "", {}
        preamble = schema[: matches[0].start()].strip()
        parts = {}
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(schema)
            chunk = schema[m.start():end].strip()
            raw_name = (m.group(1) or m.group(2) or "").strip().strip('"`[]')
            original = raw_name.split(".")[-1].strip()
            if original:
                parts.setdefault(original.lower(), (original, chunk))
        return preamble, parts

    def _link_schema(self, question: str, schema_parts: dict):
        """Ask the LLM for the needed tables/columns and parse its answer."""
        if not schema_parts:
            return set(), []
        prompt = (
            "You are given a database schema and a natural-language question.\n"
            "Identify the TABLES and COLUMNS needed to write a SQL query that "
            "answers the question.\n\n"
            "Rules:\n"
            "- Include every table the query needs, including tables used only for JOINs.\n"
            "- Include the specific columns needed for selection, filtering, "
            "joining, grouping and ordering.\n"
            "- Do NOT include irrelevant tables or columns.\n"
            '- Respond with ONLY a JSON object of the form '
            '{"tables": ["t1", "t2"], "columns": ["t1.colA", "t2.colB"]}.\n\n'
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "JSON:"
        )
        raw = self._ask(prompt, system="You are a precise database schema linking component.")
        tables, columns = self._parse_linking(raw, schema_parts)

        # Safety net: union in any table literally named in the question.
        for lower, (original, _chunk) in schema_parts.items():
            if re.search(r"\b" + re.escape(original) + r"\b", question, re.IGNORECASE):
                tables.add(lower)

        if not tables:
            # Linking produced nothing usable: degrade gracefully to full schema.
            tables = set(schema_parts.keys())
        return tables, columns

    def _parse_linking(self, raw: str, schema_parts: dict):
        """Parse the linker reply as JSON, falling back to verbatim name matching."""
        tables, columns = set(), []
        payload = None
        match = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if match:
            try:
                payload = json.loads(match.group(0))
            except (ValueError, TypeError):
                payload = None
        if isinstance(payload, dict):
            for name in payload.get("tables") or []:
                key = str(name).strip().strip('"`[]').split(".")[-1].lower()
                if key in schema_parts:
                    tables.add(key)
            for col in payload.get("columns") or []:
                col = str(col).strip()
                if col:
                    columns.append(col)
        if not tables:
            # Fallback: recover any table names mentioned verbatim in the reply.
            for lower, (original, _chunk) in schema_parts.items():
                if re.search(r"\b" + re.escape(original) + r"\b", raw or "", re.IGNORECASE):
                    tables.add(lower)
        return tables, columns

    def _render_linked_schema(self, preamble: str, schema_parts: dict, linked_tables: set) -> str:
        """Rebuild the schema text using only the linked tables."""
        if not schema_parts:
            return self.schema
        chunks = [preamble] if preamble else []
        chunks.extend(
            chunk for lower, (_original, chunk) in schema_parts.items() if lower in linked_tables
        )
        linked = "\n\n".join(c for c in chunks if c)
        return linked if linked.strip() else self.schema

    # ------------------------------------------------------------------ #
    # Stage 2 helpers: generation and repair against the linked subset
    # ------------------------------------------------------------------ #
    def _generate_sql(self, question: str, linked_schema: str, linked_columns: list) -> str:
        hint = ""
        if linked_columns:
            hint = (
                "\nRelevant columns identified by schema linking: "
                + ", ".join(linked_columns)
                + "\n"
            )
        prompt = (
            "Write a single SQL query that answers the question, using only the "
            "tables and columns shown in the schema below.\n\n"
            f"Schema (linked subset):\n{linked_schema}\n"
            f"{hint}\n"
            f"Question: {question}\n\n"
            "Requirements:\n"
            "- Output only the SQL query (optionally inside a