"""Two-stage Text-to-SQL harness: an LLM schema-linking pass first identifies the tables/columns the question mentions, then the SQL is generated (and execution-checked) against that linked schema subset."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2SchemaLink(SQLHarness):
    """Schema-link -> prune -> generate -> check harness.

    The frozen weak solver is only ever reached through ``self.llm``; the
    two-phase strategy lives in the control flow, not merely in a prompt:

      Stage 1 (LINK):     one LLM call names the tables/columns mentioned by
                          the question; the reply is parsed into Python sets.
      Stage 2 (PRUNE):    the schema text is rebuilt keeping only the CREATE
                          TABLE blocks of linked tables (the full schema is
                          the fallback whenever linking yields nothing usable).
      Stage 3 (GENERATE): one LLM call writes SQL while seeing only the
                          linked subset plus the linked-column hint list.
      Stage 4 (CHECK):    the SQL is executed once; on failure exactly one
                          bounded repair attempt is made, still constrained
                          to the linked subset.
    """

    MAX_REPAIRS = 1

    LINK_SYSTEM = (
        "You are a precise database schema linker. Given a database schema "
        "and a natural-language question, name exactly the tables and columns "
        "needed to answer that question with SQL. Include a table or column "
        "only when the question or a required join path clearly needs it."
    )

    LINK_PROMPT = (
        "Database schema:\n{schema}\n\n"
        "Question: {question}\n\n"
        "Which tables and columns are needed to answer the question? "
        "Reply ONLY in this exact format (two lines, no markdown, no "
        "explanations):\n"
        "TABLES: table1, table2\n"
        "COLUMNS: table1.column_a, table1.column_b, table2.column_c"
    )

    GEN_SYSTEM = (
        "You are a careful Text-to-SQL assistant. Write ONE valid SQL query "
        "(SQLite dialect) that answers the question, using ONLY the tables "
        "and columns present in the provided linked schema subset. Output "
        "the SQL query and nothing else."
    )

    GEN_PROMPT = (
        "Linked schema subset (only these tables may be used):\n{schema}\n\n"
        "Linked columns identified for this question: {columns}\n\n"
        "Question: {question}\n\n"
        "Write one SQL query that answers the question using only the "
        "tables/columns above. SQL:"
    )

    REPAIR_PROMPT = (
        "Linked schema subset (only these tables may be used):\n{schema}\n\n"
        "Question: {question}\n\n"
        "This SQL query failed to execute.\n"
        "SQL: {sql}\n"
        "Database error: {error}\n\n"
        "Rewrite it so it executes correctly, still using ONLY the tables "
        "and columns in the linked schema subset above. Output only the "
        "corrected SQL."
    )

    # Header of a CREATE TABLE statement; tolerant of quoting / IF NOT EXISTS.
    _CREATE_RE = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"[\"'`\[]?\s*(?P<name>[A-Za-z_][\w .\-]*?)\s*[\"'`\]]?\s*\(",
        re.IGNORECASE,
    )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def solve(self, question: str) -> str:
        # Stage 1 -- schema linking: identify tables/columns in the question.
        linked_tables, linked_columns = self._link_schema(question)

        # Stage 2 -- prune the schema to the linked subset (with fallback).
        linked_schema = self._prune_schema(linked_tables)
        if not linked_schema:
            linked_schema = self.schema
        column_hint = self._format_column_hint(linked_columns)

        # Stage 3 -- write SQL against the linked subset only.
        sql = self._generate_sql(question, linked_schema, column_hint)
        if not sql:
            # Last-resort retry against the full schema.
            sql = self._generate_sql(
                question, self.schema, "(unavailable - use the full schema above)"
            )
        if not sql:
            return ""

        # Stage 4 -- bounded execution check / repair, still on the subset.
        outcome = self._run(sql)
        if outcome.get("ok"):
            return sql
        for _ in range(self.MAX_REPAIRS):
            repaired = self._repair_sql(
                question, linked_schema, sql, outcome.get("error", "")
            )
            if not repaired or repaired == sql:
                break
            check = self._run(repaired)
            if check.get("ok"):
                return repaired
            outcome = check
        return sql

    # ------------------------------------------------------------------
    # Stage 1: schema linking
    # ------------------------------------------------------------------
    def _link_schema(self, question):
        """One LLM call -> (set of table names, {table: {columns}})."""
        try:
            response = self._as_text(
                self.llm(
                    self.LINK_PROMPT.format(schema=self.schema, question=question),
                    system=self.LINK_SYSTEM,
                    temperature=0.0,
                )
            )
        except Exception:
            return set(), {}
        return self._parse_linking(response)

    @classmethod
    def _parse_linking(cls, text):
        """Parse the strict TABLES:/COLUMNS: reply into Python structures."""
        tables, columns = set(), {}
        if not text:
            return tables, columns

        table_line = re.search(
            r"^\s*[-*•]?\s*TABLES?\s*:\s*(.+?)\s*$",
            text,
            re.IGNORECASE | re.MULTILINE,
        )
        if table_line:
            for raw in table_line.group(1).split(","):
                name = cls._clean_token(raw)
                if name and name.lower() not in {"none", "n/a", "na", "-"}:
                    tables.add(name)

        column_line = re.search(
            r"^\s*[-*•]?\s*COLUMNS?\s*:\s*(.+?)\s*$",
            text,
            re.IGNORECASE | re.MULTILINE,
        )
        if column_line:
            for raw in column_line.group(1).split(","):
                item = cls._clean_token(raw)
                if not item:
                    continue
                if "." in item:
                    tbl, col = item.split(".", 1)
                    tbl, col = tbl.strip(), col.strip()
                    if tbl:
                        tables.add(tbl)  # a linked column implies its table
                        if col and col != "*":
                            columns.setdefault(tbl, set()).add(col)
                else:
                    columns.setdefault("", set()).add(item)  # unqualified hint
        return tables, columns

    # ------------------------------------------------------------------
    # Stage 2: prune the schema to the linked subset
    # ------------------------------------------------------------------
    def _prune_schema(self, linked_tables):
        """Keep only CREATE TABLE blocks whose (normalized) name is linked."""
        if not linked_tables:
            return ""
        wanted = {self._normalize_name(t) for t in linked_tables}
        blocks = self._split_table_blocks(self.schema)
        if not blocks:
            return ""  # schema is not DDL-formatted -> caller falls back
        kept = [
            block
            for name, block in blocks
            if self._normalize_name(name) in wanted
        ]
        if not kept:
            return ""  # linker mismatched every table -> safer to keep all
        return "\n\n".join(kept)

    @classmethod
    def _split_table_blocks(cls, schema_text):
        """Return [(table_name, full CREATE TABLE statement), ...]."""
        blocks = []
        text = schema_text or ""
        for match in cls._CREATE_RE.finditer(text):
            end = text.find(";", match.end())
            end = len(text) if end == -1 else end + 1
            blocks.append((match.group("name"), text[match.start():end].strip()))
        return blocks

    @staticmethod
    def _normalize_name(name):
        cleaned = (name or "").strip().strip("\"'`[]")
        cleaned = cleaned.split(".")[-1]  # drop any db/schema qualifier
        return cleaned.strip().lower()

    # ------------------------------------------------------------------
    # Stage 3: SQL generation against the linked subset
    # ------------------------------------------------------------------
    def _generate_sql(self, question, schema_text, column_hint):
        try:
            response = self._as_text(
                self.llm(
                    self.GEN_PROMPT.format(
                        schema=schema_text, columns=column_hint, question=question
                    ),
                    system=self.GEN_SYSTEM,
                    temperature=0.0,
                )
            )
        except Exception:
            return ""
        return (bridge.extract_sql(response) or "").strip()

    # ------------------------------------------------------------------
    # Stage 4: bounded execution check / repair
    # ------------------------------------------------------------------
    def _repair_sql(self, question, schema_text, sql, error):
        try:
            response = self._as_text(
                self.llm(
                    self.REPAIR_PROMPT.format(
                        schema=schema_text, question=question, sql=sql, error=error
                    ),
                    system=self.GEN_SYSTEM,
                    temperature=0.0,
                )
            )
        except Exception:
            return ""
        return (bridge.extract_sql(response) or "").strip()

    def _run(self, sql):
        try:
            return self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

    # ------------------------------------------------------------------
    # Small utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _as_text(response):
        if isinstance(response, (list, tuple)):
            return response[0] if response else ""
        return response or ""

    @staticmethod
    def _clean_token(token):
        return (token or "").strip().strip("\"'`[];").rstrip(".").strip()

    @staticmethod
    def _format_column_hint(linked_columns):
        if not linked_columns:
            return "(no column hints available)"
        parts = []
        for table in sorted(linked_columns):
            cols = sorted(linked_columns[table])
            if table:
                parts.extend(f"{table}.{col}" for col in cols)
            else:
                parts.extend(cols)
        return ", ".join(parts) if parts else "(no column hints available)"