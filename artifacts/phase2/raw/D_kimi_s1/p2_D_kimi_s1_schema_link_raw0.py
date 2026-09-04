"""Schema-link the question to its relevant tables/columns, prune the schema to that subset, then generate and execution-repair SQL against only the linked subset."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS1SchemaLink(SQLHarness):
    """Two-stage harness: explicit schema linking first, SQL generation on the linked subset second."""

    LINK_SYSTEM = (
        "You are a database schema linker. Given a database schema and a "
        "natural-language question, identify exactly the tables and columns "
        "needed to answer the question. Output JSON only."
    )
    SQL_SYSTEM = (
        "You are an expert SQLite query writer. Use ONLY the tables and "
        "columns present in the provided linked schema subset. Return a single "
        "SQL query and nothing else."
    )
    REPAIR_SYSTEM = (
        "You are an expert SQLite query fixer. Use ONLY the tables and columns "
        "present in the provided linked schema subset. Return a single corrected "
        "SQL query and nothing else."
    )

    MAX_REPAIRS = 2

    _CLAUSE_KEYWORDS = {
        "PRIMARY", "KEY", "FOREIGN", "REFERENCES", "UNIQUE", "CHECK",
        "CONSTRAINT", "INDEX", "ON", "DELETE", "UPDATE", "CASCADE",
        "RESTRICT", "SET", "NULL", "NOT", "DEFAULT", "AUTOINCREMENT",
        "MATCH", "DEFERRABLE", "INITIALLY", "DEFERRED", "IMMEDIATE",
        "NO", "ACTION", "COLLATE", "GENERATED", "ALWAYS", "AS", "STORED",
        "VIRTUAL", "IF", "EXISTS", "TABLE", "CREATE",
    }

    _CREATE_TABLE_RE = re.compile(
        r'create\s+table\s+(?:if\s+not\s+exists\s+)?'
        r'("[^"]+"|`[^`]+`|\[[^\]]+\]|[A-Za-z_][\w$]*)\s*\(',
        re.IGNORECASE,
    )

    # ------------------------------------------------------------------ #
    # main entry point                                                    #
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        # Stage 1: identify the tables/columns mentioned by the question and
        # prune the schema down to that linked subset.
        linked_schema = self._schema_link(question)

        # Stage 2: write SQL against the linked subset only.
        sql = self._generate_sql(question, linked_schema)

        # Execution-checked repair loop, still restricted to the linked subset.
        for attempt in range(self.MAX_REPAIRS + 1):
            try:
                result = self.execute(sql)
            except Exception as exc:  # defensive: treat executor crashes as errors
                result = {"ok": False, "error": str(exc)}

            if result.get("ok"):
                return sql
            if attempt >= self.MAX_REPAIRS:
                break

            repaired = self._repair_sql(
                question, linked_schema, sql, result.get("error") or "unknown error"
            )
            if not repaired or repaired.strip() == sql.strip():
                break
            sql = repaired

        return sql

    # ------------------------------------------------------------------ #
    # stage 1: schema linking                                             #
    # ------------------------------------------------------------------ #
    def _schema_link(self, question: str) -> str:
        prompt = (
            "Question:\n"
            f"{question}\n\n"
            "Database schema:\n"
            f"{self.schema}\n\n"
            "List every table and column that may be needed to answer the "
            "question, including columns used for joining, filtering, grouping, "
            "ordering, and the final output. Return ONLY JSON of the form:\n"
            '{"tables": [{"name": "table_name", "columns": ["col_a", "col_b"]}]}\n'
            'Use an empty "columns" list to mean all columns of that table.'
        )
        raw = self._ask(prompt, self.LINK_SYSTEM)

        selection = self._parse_linking(raw)
        if selection:
            linked = self._prune_schema(selection)
            if linked:
                return linked

        # Fallback: the linker may have returned a schema subset directly.
        candidate = self._strip_fences(raw)
        if candidate and "create table" in candidate.lower() and len(candidate) <= len(self.schema or ""):
            return candidate

        # Last resort: full schema (better than an empty context).
        return self.schema or ""

    def _parse_linking(self, raw: str) -> dict:
        text = self._strip_fences(raw)
        obj = None
        try:
            obj = json.loads(text)
        except Exception:
            for opener, closer in (("{", "}"), ("[", "]")):
                start, end = text.find(opener), text.rfind(closer)
                if start != -1 and end > start:
                    try:
                        obj = json.loads(text[start:end + 1])
                        break
                    except Exception:
                        continue
        if obj is None:
            return {}
        return self._linking_from_json(obj)

    def _linking_from_json(self, obj) -> dict:
        selection = {}

        def add(name, cols):
            if name is None:
                return
            key = str(name).strip().strip('"`[]').split(".")[-1].lower()
            if not key:
                return
            bucket = selection.setdefault(key, set())
            if cols:
                for col in cols:
                    col_name = str(col).strip().strip('"`[]').split(".")[-1].lower()
                    if col_name and col_name != "*":
                        bucket.add(col_name)

        if isinstance(obj, dict):
            tables = obj.get("tables")
            if isinstance(tables, list):
                for entry in tables:
                    if isinstance(entry, str):
                        add(entry, [])
                    elif isinstance(entry, dict):
                        add(
                            entry.get("name") or entry.get("table") or entry.get("table_name"),
                            entry.get("columns") or entry.get("cols") or [],
                        )
            else:
                for key, value in obj.items():
                    if str(key).lower() in {"tables", "question", "reasoning", "explanation", "notes"}:
                        continue
                    if isinstance(value, (list, tuple)):
                        add(key, value)
                    elif isinstance(value, dict):
                        add(key, value.get("columns") or value.get("cols") or [])
        elif isinstance(obj, list):
            for entry in obj:
                if isinstance(entry, str):
                    add(entry, [])
                elif isinstance(entry, dict):
                    add(
                        entry.get("name") or entry.get("table") or entry.get("table_name"),
                        entry.get("columns") or entry.get("cols") or [],
                    )
        return selection

    def _prune_schema(self, selection: dict) -> str:
        kept_statements = []
        for chunk in self._split_statements(self.schema or ""):
            stmt = chunk.strip()
            if not stmt:
                continue
            token, body = self._parse_create_table(stmt)
            if token is None:
                continue
            key = token.strip('"`[]').lower()
            if key not in selection:
                continue

            cols = selection[key]
            if not cols:
                # Linker asked for the whole table.
                kept_statements.append(stmt.rstrip(";") + ";")
                continue

            kept_parts = []
            for part in self._split_top_level(body):
                col = self._column_of(part)
                if col is not None:
                    if col.lower() in cols:
                        kept_parts.append(part.strip())
                elif self._constraint_within(part, cols):
                    kept_parts.append(part.strip())

            if kept_parts:
                kept_statements.append(
                    "CREATE TABLE {} (\n  {}\n);".format(token, ",\n  ".join(kept_parts))
                )
            else:
                kept_statements.append(stmt.rstrip(";") + ";")

        return "\n\n".join(kept_statements)

    # ------------------------------------------------------------------ #
    # stage 2: SQL generation / repair                                    #
    # ------------------------------------------------------------------ #
    def _generate_sql(self, question: str, linked_schema: str) -> str:
        prompt = (
            "Linked schema subset (use NOTHING outside these tables/columns):\n"
            f"{linked_schema}\n\n"
            "Question:\n"
            f"{question}\n\n"
            "Write one SQLite query that answers the question. Return only the SQL."
        )
        return self._extract_sql(self._ask(prompt, self.SQL_SYSTEM))

    def _repair_sql(self, question: str, linked_schema: str, sql: str, error: str) -> str:
        prompt = (
            "Linked schema subset (use NOTHING outside these tables/columns):\n"
            f"{linked_schema}\n\n"
            "Question:\n"
            f"{question}\n\n"
            "Previous SQL:\n"
            f"{sql}\n\n"
            "Execution error:\n"
            f"{error}\n\n"
            "Return one corrected SQLite query. Return only the SQL."
        )
        return self._extract_sql(self._ask(prompt, self.REPAIR_SYSTEM))

    # ------------------------------------------------------------------ #
    # small utilities                                                     #
    # ------------------------------------------------------------------ #
    def _ask(self, prompt: str, system: str) -> str:
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return "" if out is None else str(out)

    def _extract_sql(self, raw: str) -> str:
        sql = ""
        try:
            sql = bridge.extract_sql(raw) or ""
        except Exception:
            sql = ""
        if not sql.strip():
            sql = self._strip_fences(raw)
        return sql.strip()

    @staticmethod
    def _strip_fences(text: str) -> str:
        text = (text or "").strip()
        if text.startswith("