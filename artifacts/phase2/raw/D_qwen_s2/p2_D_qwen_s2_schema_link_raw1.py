"""Harness that first schema-links the question to relevant tables/columns and then generates SQL against that linked subset."""

import ast
import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        parsed_schema = self._parse_schema(schema)

        linked_tables, linked_columns = self._link_schema(question, parsed_schema)
        linked_schema = self._render_linked_schema(parsed_schema, linked_tables, linked_columns)
        if not linked_schema.strip():
            linked_schema = schema

        sql = self._generate_sql(question, linked_schema)
        best_sql = sql

        if sql:
            current = sql
            for _ in range(3):
                result = self._safe_execute(current)
                if result.get("ok"):
                    return current

                best_sql = current
                repaired = self._repair_sql(
                    question,
                    linked_schema,
                    current,
                    result.get("error") or "",
                )
                if not repaired or self._same_sql(repaired, current):
                    break
                current = repaired

            if not self._same_sql(current, best_sql):
                result = self._safe_execute(current)
                if result.get("ok"):
                    return current
                best_sql = current

        return best_sql or ""

    def _same_sql(self, a, b):
        def normalize(sql):
            sql = (sql or "").strip().rstrip(";").strip()
            return re.sub(r"\s+", " ", sql).lower()

        return normalize(a) == normalize(b)

    def _parse_schema(self, schema):
        tables = []
        if not schema:
            return tables

        name_part = r"(?:`[^`]+`|\"[^\"]+\"|\[[^\]]+\]|[\w\-]+)"
        qualified_name = name_part + r"(?:\s*\.\s*" + name_part + r")*"
        create_re = re.compile(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMPORARY\s+)?(?:EXTERNAL\s+)?TABLE\s+"
            r"(?:IF\s+NOT\s+EXISTS\s+)?(" + qualified_name + r")",
            re.IGNORECASE,
        )

        for match in create_re.finditer(schema):
            raw_name = re.sub(r"[`\"\[\]]", "", match.group(1)).strip()
            base_name = raw_name.split(".")[-1].strip()

            paren_start = schema.find("(", match.end())
            if paren_start == -1:
                continue

            depth = 0
            end = None
            in_quote = None
            escape = False

            for idx in range(paren_start, len(schema)):
                ch = schema[idx]
                if in_quote:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == in_quote:
                        in_quote = None
                else:
                    if ch in ("`", '"', "'"):
                        in_quote = ch
                    elif ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            end = idx
                            break

            if end is None:
                continue

            body = schema[paren_start + 1:end]
            column_names = []
            column_defs = {}
            constraints = []

            for part in self._split_top_level(body):
                part = part.strip()
                if not part:
                    continue

                if self._is_constraint(part):
                    constraints.append(part)
                    continue

                column = self._extract_column_name(part)
                if column:
                    column_names.append(column)
                    column_defs[column.lower()] = part

            tables.append(
                {
                    "name": base_name,
                    "raw_name": raw_name,
                    "columns": column_names,
                    "column_defs": column_defs,
                    "constraints": constraints,
                    "raw": schema[match.start():end + 1],
                }
            )

        return tables

    def _split_top_level(self, text):
        parts = []
        current = []
        depth = 0
        in_quote = None
        escape = False

        for ch in text:
            if in_quote:
                current.append(ch)
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == in_quote:
                    in_quote = None
            else:
                if ch in ("`", '"', "'"):
                    in_quote = ch
                    current.append(ch)
                elif ch == "(":
                    depth += 1
                    current.append(ch)
                elif ch == ")":
                    depth -= 1
                    current.append(ch)
                elif ch == "," and depth == 0:
                    parts.append("".join(current))
                    current = []
                else:
                    current.append(ch)

        if current:
            parts.append("".join(current))

        return parts

    def _is_constraint(self, part):
        head = part.strip().upper()
        return head.startswith(
            (
                "PRIMARY KEY",
                "FOREIGN KEY",
                "UNIQUE",
                "CONSTRAINT",
                "CHECK",
                "KEY",
                "INDEX",
                "FULLTEXT",
                "SPATIAL",
                "REFERENCES",
            )
        )

    def _extract_column_name(self, part):
        part = part.strip()
        patterns = (
            r"^`([^`]+)`",
            r'^"([^"]+)"',
            r"^\[([^\]]+)\]",
            r"^([\w\-]+)",
        )
        for pattern in patterns:
            match = re.match(pattern, part)
            if match:
                return match.group(1)
        return ""

    def _link_schema(self, question, parsed_schema):
        if not parsed_schema:
            return set(), {}

        known_tables = {table["name"].lower(): table for table in parsed_schema}
        column_to_tables = {}
        for table in parsed_schema:
            for column in table["columns"]:
                column_to_tables.setdefault(column.lower(), set()).add(table["name"].lower())

        tables = set()
        columns = {}

        llm_link = self._llm_link(question, parsed_schema)
        if llm_link is not None:
            tables, columns = self._normalize_link(llm_link, known_tables, column_to_tables)

        if not tables and not columns:
            tables, columns = self._keyword_link(question, parsed_schema)

        for table, cols in list(columns.items()):
            if cols:
                tables.add(table)

        cleaned_tables = set()
        cleaned_columns = {}

        for table in tables:
            table_l = str(table).lower()
            if table_l not in known_tables:
                continue

            cleaned_tables.add(table_l)
            selected = {str(column).lower() for column in columns.get(table, set()) if column}
            valid = {column.lower() for column in known_tables[table_l]["columns"]}
            selected = {column for column in selected if column in valid}

            if selected:
                cleaned_columns[table_l] = selected

        for table in cleaned_columns:
            cleaned_tables.add(table)

        return cleaned_tables, cleaned_columns

    def _llm_link(self, question, parsed_schema):
        lines = []
        for table in parsed_schema[:120]:
            cols = ", ".join(table["columns"][:120])
            lines.append(f"{table['name']} ({cols})")

        schema_brief = "\n".join(lines) if lines else "No schema available."
        if len(schema_brief) > 16000:
            schema_brief = schema_brief[:16000] + "\n-- truncated"

        prompt = (
            "Identify the database tables and columns needed to answer the question.\n"
            "Return ONLY a JSON object of the form: {\"tables\": [\"table_name\"], \"columns\": {\"table_name\": [\"column_name\"]}}.\n"
            "If a table is needed but no specific columns are known, include it in \"tables\" and omit it from \"columns\".\n"
            "Do not include explanations, SQL, or markdown.\n\n"
            f"Schema:\n{schema_brief}\n\n"
            f"Question: {question}\n"
        )

        try:
            response = self.llm(
                prompt,
                system="You are a precise SQL schema linker.",
                temperature=0.0,
                n=1,
            )
        except Exception:
            return None

        return self._extract_json(response)

    def _extract_json(self, text):
        text = self._to_text(text).strip()
        if not text:
            return None

        candidates = []
        fence = re.search(r"