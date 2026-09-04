"""Schema-linking harness that first identifies relevant tables/columns and then generates SQL against that linked subset."""
import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS1SchemaLink(SQLHarness):
    MAX_REPAIR_ATTEMPTS = 2
    _CONSTRAINT_KEYWORDS = frozenset({
        "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT",
        "INDEX", "KEY", "EXCLUDE", "FULLTEXT", "SPATIAL", "CONSTRAINTS",
    })

    def solve(self, question: str) -> str:
        raw_schema = self.schema
        if isinstance(raw_schema, (list, tuple)):
            full_schema = "\n".join(str(item) for item in raw_schema)
        else:
            full_schema = str(raw_schema or "")

        parsed_schema = self._parse_schema(full_schema)
        linked_schema, _ = self._build_linked_schema(question, full_schema, parsed_schema)

        sql = self._generate_sql(question, linked_schema, full_schema)
        if not sql:
            sql = self._fallback_sql(question, full_schema)

        for attempt in range(self.MAX_REPAIR_ATTEMPTS + 1):
            sql = (sql or "").strip().rstrip(";").strip()
            if not sql:
                sql = self._fallback_sql(question, full_schema)

            result = self._safe_execute(sql)
            if result.get("ok"):
                return sql

            error = str(result.get("error") or "unknown error")
            if attempt == self.MAX_REPAIR_ATTEMPTS:
                break

            repair_schema = full_schema if self._looks_like_schema_error(error) else linked_schema
            repaired = self._extract_sql(self._call_llm(
                self._repair_prompt(question, repair_schema, sql, error),
                "You are a careful SQL repairer."
            ))

            if not repaired and repair_schema != full_schema:
                repaired = self._extract_sql(self._call_llm(
                    self._repair_prompt(question, full_schema, sql, error),
                    "You are a careful SQL repairer."
                ))

            if not repaired or repaired.strip().lower() == sql.strip().lower():
                break

            sql = repaired

        return sql or "SELECT 1"

    def _call_llm(self, prompt, system):
        try:
            return self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""

    def _generate_sql(self, question, linked_schema, full_schema):
        schema_text = linked_schema or full_schema
        prompt = "\n".join([
            "Write one valid SQL query to answer the question.",
            "Use ONLY the following linked schema subset.",
            "Use exact table and column names from the schema.",
            "Return ONLY the SQL query, no explanation.",
            "",
            "Linked schema subset:",
            schema_text,
            "",
            "Question: " + question,
        ])
        return self._extract_sql(self._call_llm(prompt, "You are an expert SQL generator."))

    def _fallback_sql(self, question, full_schema):
        prompt = "\n".join([
            "Write one valid SQL query to answer the question using the schema.",
            "Return ONLY the SQL query, no explanation.",
            "",
            "Schema:",
            full_schema,
            "",
            "Question: " + question,
        ])
        return self._extract_sql(self._call_llm(prompt, "You are an expert SQL generator."))

    def _repair_prompt(self, question, schema, sql, error):
        return "\n".join([
            "The following SQL query failed.",
            "Error: " + error,
            "Repair the query so it is valid for the schema and answers the question.",
            "Return ONLY the corrected SQL query.",
            "",
            "Schema:",
            schema,
            "",
            "Question: " + question,
            "",
            "Broken SQL:",
            sql,
        ])

    def _build_linked_schema(self, question, full_schema, parsed_schema):
        if not parsed_schema:
            return full_schema, []

        links = self._get_schema_links(question, full_schema, parsed_schema)
        raw_tables = links.get("tables") or []
        raw_columns = links.get("columns") or {}

        if not raw_tables and raw_columns:
            raw_tables = list(raw_columns.keys())

        mapped_tables = []
        requested_columns = {}

        for raw_table in raw_tables:
            norm_table = self._match_table(raw_table, parsed_schema)
            if not norm_table or norm_table in mapped_tables:
                continue

            mapped_tables.append(norm_table)

            cols = []
            keys_to_try = [
                raw_table,
                self._norm_name(raw_table),
                parsed_schema[norm_table]["name"],
                norm_table,
            ]

            for key in keys_to_try:
                if key in raw_columns:
                    value = raw_columns[key]
                    if isinstance(value, str):
                        value = [value]
                    if isinstance(value, list):
                        cols = value
                        break

            if not cols:
                for key, value in raw_columns.items():
                    if self._match_table(key, parsed_schema) == norm_table:
                        if isinstance(value, str):
                            value = [value]
                        if isinstance(value, list):
                            cols = value
                            break

            if cols:
                requested_columns[norm_table] = cols

        if not mapped_tables:
            qnorm = self._norm_text(question)
            qtokens = set(re.findall(r"[a-z0-9_]+", qnorm))
            for norm_table, info in parsed_schema.items():
                table_name = self._norm_name(info["name"])
                if (
                    norm_table in qtokens
                    or table_name in qtokens
                    or self._singular(norm_table) in qtokens
                    or self._singular(table_name) in qtokens
                    or norm_table in qnorm
                    or table_name in qnorm
                ):
                    mapped_tables.append(norm_table)

        if not mapped_tables:
            return full_schema, []

        question_tokens = set(re.findall(r"[a-z0-9_]+", self._norm_text(question)))
        final_columns = {}

        for norm_table in mapped_tables:
            if norm_table not in requested_columns:
                continue

            table_columns = parsed_schema[norm_table]["columns"]
            selected = set()

            for raw_col in requested_columns[norm_table]:
                matched = self._match_column(raw_col, table_columns)
                if matched:
                    selected.add(matched)

            for col in table_columns:
                if col in question_tokens:
                    selected.add(col)

            singular_table = self._singular(norm_table)
            for col in table_columns:
                if (
                    col == "id"
                    or col.endswith("_id")
                    or col == norm_table + "_id"
                    or col == singular_table + "_id"
                ):
                    selected.add(col)

            if selected:
                final_columns[norm_table] = selected

        statements = []
        for norm_table in mapped_tables:
            info = parsed_schema[norm_table]
            selected = final_columns.get(norm_table)

            if not selected:
                statements.append(info["raw"])
                continue

            lines = []
            for col_norm, col_info in info["columns"].items():
                if col_norm in selected:
                    lines.append(col_info["line"])

            if not lines:
                statements.append(info["raw"])
            else:
                statements.append(
                    "CREATE TABLE " + info["name"] + " (\n  " + ",\n  ".join(lines) + "\n)"
                )

        linked_schema = ";\n\n".join(statements)
        if linked_schema:
            linked_schema += ";"

        return linked_schema, mapped_tables

    def _get_schema_links(self, question, full_schema, parsed_schema):
        schema_text = self._schema_for_linking(full_schema, parsed_schema)
        prompt = "\n".join([
            "Identify the minimal tables and columns needed to answer the question.",
            "Return ONLY valid JSON with this exact shape:",
            '{"tables": ["table_name"], "columns": {"table_name": ["column_name"]}}',
            "Include tables needed for SELECT, WHERE, JOIN, GROUP BY, ORDER BY, and required join paths.",
            "Include columns needed for SELECT, filters, joins, grouping, ordering, and aggregation.",
            "Use exact table and column names from the schema. If unsure, include extra rather than missing.",
            "",
            "Schema:",
            schema_text,
            "",
            "Question: " + question,
        ])

        text = self._call_llm(prompt, "You are a precise schema linker for SQL.")
        data = self._extract_json(text)

        tables = []
        columns = {}

        if isinstance(data, dict):
            raw_tables = data.get("tables")
            if isinstance(raw_tables, str):
                raw_tables = [raw_tables]

            if isinstance(raw_tables, list):
                for item in raw_tables:
                    if isinstance(item, str) and item.strip():
                        tables.append(item.strip().strip('`"[]'))
                    elif isinstance(item, (int, float)):
                        tables.append(str(item))

            raw_columns = data.get("columns")
            if isinstance(raw_columns, dict):
                for key, value in raw_columns.items():
                    if not isinstance(key, str):
                        continue

                    if isinstance(value, str):
                        value = [value]

                    if not isinstance(value, list):
                        continue

                    clean = []
                    for item in value:
                        if isinstance(item, str) and item.strip():
                            clean.append(item.strip().strip('`"[]'))
                        elif isinstance(item, (int, float)):
                            clean.append(str(item))

                    if clean:
                        columns[key.strip()] = clean

        if not tables and columns:
            tables = list(columns.keys())

        if not tables:
            qnorm = self._norm_text(question)
            qtokens = set(re.findall(r"[a-z0-9_]+", qnorm))
            for norm_table, info in parsed_schema.items():
                table_name = self._norm_name(info["name"])
                if (
                    norm_table in qtokens
                    or table_name in qtokens
                    or self._singular(norm_table) in qtokens
                    or self._singular(table_name) in qtokens
                    or norm_table in qnorm
                    or table_name in qnorm
                ):
                    tables.append(info["name"])

        return {"tables": tables, "columns": columns}

    def _schema_for_linking(self, full_schema, parsed_schema):
        if not parsed_schema:
            return full_schema

        if len(full_schema) <= 12000:
            return full_schema

        lines = []
        for info in parsed_schema.values():
            cols = ", ".join(col_info["name"] for col_info in info["columns"].values())
            if cols:
                lines.append("CREATE TABLE " + info["name"] + " (" + cols + ");")
            else:
                lines.append("CREATE TABLE " + info["name"] + " ();")

        return "\n".join(lines)

    def _extract_json(self, text):
        if not text:
            return {}

        if isinstance(text, list):
            text = text[0] if text else ""

        if not isinstance(text, str):
            text = str(text)

        text = text.strip()
        text = re.sub(r"^