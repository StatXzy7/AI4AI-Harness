"""Two-stage schema-linking harness: first identifies relevant tables/columns from the question, then generates SQL against that linked subset."""

import json
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        link = self._link_schema(question)
        linked_schema = self._build_linked_schema(link)

        sql = self._generate_sql(question, linked_schema, link)

        if not sql:
            repaired = self._repair_sql(question, linked_schema, link, "", "")
            return repaired or ""

        try:
            result = self.execute(sql)
        except Exception as exc:
            result = {"ok": False, "rows": [], "error": str(exc)}

        if not result.get("ok"):
            repaired = self._repair_sql(
                question, linked_schema, link, sql, result.get("error", "")
            )
            if repaired:
                return repaired

        return sql

    def _link_schema(self, question: str):
        prompt = f"""You are a database schema linker. Given a natural language question and a database schema, identify the minimal set of tables and columns needed to write the SQL query.

Database schema:
{self.schema}

Question:
{question}

Respond with a JSON object only, in the following format:
{{"tables": ["table_name"], "columns": ["table_name.column_name"]}}

Use only exact names from the schema. If a table is relevant but all columns are needed, list only the table and omit its columns."""
        response = self._call_llm(prompt)
        return self._parse_link(response)

    def _parse_link(self, response: str):
        data = None
        try:
            data = json.loads(response)
        except Exception:
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:
                    data = None

        if not isinstance(data, dict):
            data = {}

        tables = data.get("tables", []) or []
        columns = data.get("columns", []) or []

        if not isinstance(tables, list):
            tables = []
        if not isinstance(columns, list):
            columns = []

        tables = [str(t).strip() for t in tables if str(t).strip()]
        columns = [str(c).strip() for c in columns if str(c).strip()]

        return {"tables": tables, "columns": columns}

    def _build_linked_schema(self, link):
        tables = link.get("tables", [])
        columns = link.get("columns", [])

        if not tables and not columns:
            return self.schema

        parsed = self._parse_schema_tables(self.schema)
        if not parsed:
            return self.schema

        selected_tables = set(t.lower() for t in tables)
        table_cols = {}

        for col_ref in columns:
            if "." in col_ref:
                table_part, col_part = col_ref.split(".", 1)
                t_key = table_part.strip().lower()
                col_key = col_part.strip().lower()
                if t_key:
                    selected_tables.add(t_key)
                    table_cols.setdefault(t_key, set()).add(col_key)
            else:
                col_key = col_ref.strip().lower()
                for t_key, block in parsed.items():
                    if col_key in self._extract_columns_from_block(block):
                        selected_tables.add(t_key)
                        table_cols.setdefault(t_key, set()).add(col_key)

        if not selected_tables:
            selected_tables = set(table_cols.keys())

        if not selected_tables:
            return self.schema

        fragments = []
        for t_key in sorted(selected_tables):
            block = parsed.get(t_key)
            if not block:
                continue

            cols = table_cols.get(t_key)
            if not cols:
                fragments.append(block)
            else:
                fragments.append(self._filter_table_block(block, t_key, cols))

        return "\n\n".join(fragments) if fragments else self.schema

    def _parse_schema_tables(self, schema: str):
        tables = {}
        pattern = re.compile(
            r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"\[]?([\w\.$]+)[`"\]]?\s*\(',
            re.IGNORECASE,
        )

        for match in pattern.finditer(schema):
            name = match.group(1)
            start = match.end() - 1
            end = self._find_matching_paren(schema, start)
            if end == -1:
                continue

            tail = end + 1
            while tail < len(schema) and schema[tail].isspace():
                tail += 1
            if tail < len(schema) and schema[tail] == ";":
                tail += 1

            block = schema[match.start():tail]
            tables[name.lower()] = block

        return tables

    def _find_matching_paren(self, text: str, start: int):
        depth = 0
        in_single = False
        in_double = False

        for i in range(start, len(text)):
            ch = text[i]
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == "(" and not in_single and not in_double:
                depth += 1
            elif ch == ")" and not in_single and not in_double:
                depth -= 1
                if depth == 0:
                    return i

        return -1

    def _body_from_block(self, block: str):
        start = block.find("(")
        if start == -1:
            return ""
        end = self._find_matching_paren(block, start)
        if end == -1:
            return ""
        return block[start + 1:end]

    def _split_top_level(self, text: str):
        parts = []
        current = []
        depth = 0
        in_single = False
        in_double = False

        for ch in text:
            if ch == "'" and not in_double:
                in_single = not in_single
                current.append(ch)
            elif ch == '"' and not in_single:
                in_double = not in_double
                current.append(ch)
            elif ch == "(" and not in_single and not in_double:
                depth += 1
                current.append(ch)
            elif ch == ")" and not in_single and not in_double:
                depth -= 1
                current.append(ch)
            elif ch == "," and depth == 0 and not in_single and not in_double:
                parts.append("".join(current))
                current = []
            else:
                current.append(ch)

        if current:
            parts.append("".join(current))

        return parts

    def _extract_column_name(self, part: str):
        part = part.strip()
        if re.match(r'(?i)(PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|CHECK|CONSTRAINT)', part):
            return None

        match = re.match(r'[`"\[]?([\w$]+)[`"\]]?', part)
        if match:
            return match.group(1).lower()

        return None

    def _extract_columns_from_block(self, block: str):
        body = self._body_from_block(block)
        if not body:
            return set()

        cols = set()
        for part in self._split_top_level(body):
            col = self._extract_column_name(part)
            if col:
                cols.add(col)

        return cols

    def _filter_table_block(self, block: str, table_key: str, cols):
        body = self._body_from_block(block)
        if not body:
            return block

        parts = self._split_top_level(body)
        kept = []
        for part in parts:
            col = self._extract_column_name(part)
            if col is not None and col in cols:
                kept.append(part.strip())

        if not kept:
            return block

        start = block.find("(")
        end = self._find_matching_paren(block, start)
        if start == -1 or end == -1:
            return block

        return block[:start + 1] + "\n" + ",\n".join(kept) + "\n" + block[end:]

    def _generate_sql(self, question: str, linked_schema: str, link):
        prompt = self._build_sql_prompt(question, linked_schema, link)
        response = self._call_llm(prompt)
        return bridge.extract_sql(response)

    def _repair_sql(self, question: str, linked_schema: str, link, previous_sql: str, error: str):
        prompt = self._build_repair_prompt(question, linked_schema, link, previous_sql, error)
        response = self._call_llm(prompt)
        return bridge.extract_sql(response)

    def _build_sql_prompt(self, question: str, linked_schema: str, link):
        link_lines = []
        if link.get("tables"):
            link_lines.append("Relevant tables: " + ", ".join(link["tables"]))
        if link.get("columns"):
            link_lines.append("Relevant columns: " + ", ".join(link["columns"]))
        link_desc = "\n".join(link_lines)
        if link_desc:
            link_desc = "\n" + link_desc

        return f"""You are an expert SQL writer. Use only the linked schema subset below to answer the question.

Linked schema subset:
{linked_schema}

Question:
{question}
{link_desc}

Return only the SQL query, with no explanation."""

    def _build_repair_prompt(self, question: str, linked_schema: str, link, previous_sql: str, error: str):
        previous = previous_sql if previous_sql else "(no SQL was produced)"
        error = error if error else "No SQL was produced"

        return f"""You are an expert SQL writer. The following SQL query was generated for the question but failed or was missing.

Linked schema subset:
{linked_schema}

Question:
{question}

Previous SQL:
{previous}

Execution error:
{error}

Return only the corrected SQL query, with no explanation."""

    def _call_llm(self, prompt: str, system: str = ""):
        result = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(result, list):
            return result[0] if result else ""
        if result is None:
            return ""
        return str(result)