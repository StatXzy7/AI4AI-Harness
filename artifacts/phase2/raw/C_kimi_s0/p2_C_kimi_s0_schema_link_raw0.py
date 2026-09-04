"""Harness that first performs explicit LLM-based schema linking to isolate the question-relevant tables/columns, then generates SQL constrained to that linked subset with execution-feedback retries."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS0SchemaLink(SQLHarness):
    """Two-stage harness: (1) link the question to a subset of schema tables/columns,
    (2) generate SQL against only that linked subset, retrying on execution errors."""

    _TABLE_RE = re.compile(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?(?P<name>[A-Za-z0-9_. ]+?)["`\]]?\s*\(',
        re.IGNORECASE,
    )
    _CONSTRAINT_KEYWORDS = ("primary", "foreign", "unique", "check", "constraint", "key")

    MAX_ATTEMPTS = 3

    # ------------------------------------------------------------------ main
    def solve(self, question: str) -> str:
        # Stage 1: schema linking -- identify tables/columns mentioned by the question.
        tables = self._parse_schema_tables(self.schema)
        linked = self._link_schema(question, tables)
        linked_schema = self._build_linked_schema(tables, linked)

        # Stage 2: SQL generation against the linked subset, with error feedback.
        feedback = ""
        last_sql = ""
        for _ in range(self.MAX_ATTEMPTS):
            raw = self._generate_sql(question, linked_schema, feedback)
            sql = bridge.extract_sql(raw) or raw.strip()
            if not sql:
                continue
            last_sql = sql
            result = self.execute(sql)
            if result.get("ok"):
                return sql
            feedback = str(result.get("error", "")).strip()
        return last_sql

    # -------------------------------------------------------- schema parsing
    def _parse_schema_tables(self, schema):
        """Split the schema into per-table chunks keyed by lowercased table name."""
        schema = schema or ""
        matches = list(self._TABLE_RE.finditer(schema))
        tables = {}
        for i, m in enumerate(matches):
            name = m.group("name").strip().strip('"`[]')
            end = matches[i + 1].start() if i + 1 < len(matches) else len(schema)
            chunk = schema[m.start():end].strip()
            tables[name.lower()] = (name, chunk)
        return tables

    @staticmethod
    def _split_top_level(text):
        """Split on commas that are not nested inside parentheses."""
        parts, depth, current = [], 0, []
        for ch in text:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            if ch == "," and depth == 0:
                parts.append("".join(current))
                current = []
            else:
                current.append(ch)
        if current:
            parts.append("".join(current))
        return parts

    def _columns_of(self, chunk):
        """Extract the column names declared in a CREATE TABLE chunk."""
        start = chunk.find("(")
        end = chunk.rfind(")")
        if start == -1 or end <= start:
            return set()
        cols = set()
        for part in self._split_top_level(chunk[start + 1:end]):
            token = part.strip()
            if not token:
                continue
            first = token.split()[0].strip('"`[]')
            if first.lower() in self._CONSTRAINT_KEYWORDS:
                continue
            cols.add(first.lower())
        return cols

    # ------------------------------------------------------ stage 1: linking
    def _link_schema(self, question, tables):
        system = (
            "You are a schema-linking expert for Text-to-SQL. "
            "Identify exactly the tables and columns the question refers to."
        )
        prompt = (
            "Database schema:\n" + (self.schema or "") + "\n\n"
            "Question: " + question + "\n\n"
            "Which tables and columns from the schema are needed to answer the question? "
            "Respond with ONLY a JSON object mapping each relevant table name to a list of its "
            "relevant column names, e.g. "
            '{"table1": ["col1", "col2"], "table2": ["col3"]}. '
            "Use the exact table and column names as they appear in the schema. "
            "Do not output anything else."
        )
        raw = self._as_text(self.llm(prompt, system=system, temperature=0.0, n=1))
        return self._parse_linking(raw, tables)

    def _parse_linking(self, raw, tables):
        """Parse the linker's JSON output into {table_key: [columns]}; fall back to
        name matching, and ultimately to the full schema (empty dict -> caller handles)."""
        linked = {}
        candidate = None
        if raw:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end > start:
                candidate = raw[start:end + 1]
        if candidate:
            try:
                data = json.loads(candidate)
            except Exception:
                data = None
            if isinstance(data, dict):
                for tname, cols in data.items():
                    key = str(tname).strip().strip('"`[]').lower()
                    if key in tables:
                        if isinstance(cols, (list, tuple)):
                            linked[key] = [str(c).strip().strip('"`[]') for c in cols]
                        else:
                            linked[key] = []
        if linked:
            return linked
        # Fallback: mark any table whose name literally appears in the response.
        lowered = (raw or "").lower()
        for key in tables:
            if key in lowered:
                linked[key] = []
        return linked

    def _build_linked_schema(self, tables, linked):
        """Build the reduced schema containing only the linked tables, annotated
        with the linked columns. Falls back to the full schema when linking fails."""
        if not tables or not linked:
            return self.schema or ""
        parts = []
        for key, cols in linked.items():
            name, chunk = tables[key]
            if cols:
                known = self._columns_of(chunk)
                keep = [c for c in cols if not known or c.lower() in known]
                if keep:
                    chunk += "\n-- question-relevant columns in {}: {}".format(
                        name, ", ".join(keep)
                    )
            parts.append(chunk)
        return "\n\n".join(parts) if parts else (self.schema or "")

    # ----------------------------------------------------- stage 2: generate
    def _generate_sql(self, question, linked_schema, feedback):
        system = (
            "You are an expert Text-to-SQL generator. "
            "Output only a single syntactically valid SQL query."
        )
        prompt = (
            "The database schema below has been reduced to the tables/columns linked "
            "to the question. Use ONLY this linked schema.\n\n"
            "Linked schema:\n" + linked_schema + "\n\n"
            "Question: " + question + "\n\n"
        )
        if feedback:
            prompt += (
                "A previous SQL attempt failed with this database error:\n"
                + feedback
                + "\nCorrect the query accordingly.\n\n"
            )
        prompt += (
            "Write one SQL query that answers the question using only the tables "
            "and columns in the linked schema above. Return only the SQL query."
        )
        return self._as_text(self.llm(prompt, system=system, temperature=0.0, n=1))

    # ------------------------------------------------------------------ util
    @staticmethod
    def _as_text(response):
        if isinstance(response, (list, tuple)):
            return "" if not response else str(response[0])
        return "" if response is None else str(response)