"""Schema-linking harness that first identifies relevant tables/columns and then generates SQL against that linked subset."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        schema_text = (self.schema or "").strip()
        tables = self._parse_schema(schema_text)
        linked_tables, linked_columns = self._link_schema(question, schema_text, tables)

        candidates = []
        subset_schema = self._render_subset_schema(tables, linked_tables, linked_columns)
        if subset_schema:
            candidates.append(("linked", subset_schema))

        if schema_text and self._canonical_schema(subset_schema) != self._canonical_schema(schema_text):
            candidates.append(("full", schema_text))

        if not candidates and schema_text:
            candidates.append(("full", schema_text))

        best_sql = ""
        for mode, schema_for_prompt in candidates:
            active_columns = linked_columns if mode == "linked" else set()
            sql = self._generate_sql(question, schema_for_prompt, active_columns)
            if not sql:
                continue

            best_sql = sql
            ok, err = self._execute_ok(sql)
            if ok:
                return sql

            current = sql
            for _ in range(2):
                repaired = self._repair_sql(question, current, err, schema_for_prompt, active_columns)
                if not repaired or repaired == current:
                    break

                best_sql = repaired
                ok, err = self._execute_ok(repaired)
                if ok:
                    return repaired
                current = repaired

        if not best_sql:
            prompt = (
                "Write a SQL query for the following request. Return only SQL.\n"
                f"Question: {question}"
            )
            best_sql = self._extract_sql(
                self._llm_text(prompt, system="You are an expert SQL generator.")
            )

        return best_sql or "SELECT 1"

    def _canonical_schema(self, text):
        return re.sub(r"\s+", " ", (text or "").strip()).lower()

    def _link_schema(self, question, schema_text, tables):
        if not tables:
            return set(), set()

        system = "You are a precise schema linker for a SQL database. Output only JSON."
        prompt = (
            "Identify the database tables and columns that are mentioned or required by the question.\n"
            "Return only valid JSON with this shape:\n"
            '{"tables": ["table_name"], "columns": [{"table": "table_name", "column": "column_name"}]}\n'
            "Use exact names from the schema. Include only relevant objects.\n\n"
            f"Schema:\n{schema_text}\n\n"
            f"Question:\n{question}\n"
        )

        text = self._llm_text(prompt, system=system, temperature=0.0, n=1)
        data = self._extract_json(text)

        raw_tables, raw_columns = [], []
        if data is not None:
            raw_tables, raw_columns = self._parse_link_output(data)

        if not raw_tables and not raw_columns:
            raw_tables, raw_columns = self._lexical_link(question, tables)

        linked_tables = set()
        linked_columns = set()

        for table_candidate in raw_tables:
            if isinstance(table_candidate, dict):
                expanded = []
                self._collect_tables(table_candidate, expanded)
                for item in expanded:
                    matched = self._match_table(item, tables)
                    if matched:
                        linked_tables.add(matched)
            else:
                matched = self._match_table(table_candidate, tables)
                if matched:
                    linked_tables.add(matched)

        for column_candidate in raw_columns:
            table_part = ""
            column_part = ""

            if isinstance(column_candidate, dict):
                tmp = []
                self._collect_columns(column_candidate, tmp, is_item=True)
                if tmp:
                    table_part, column_part = tmp[0]
            elif isinstance(column_candidate, (list, tuple)):
                if len(column_candidate) == 2:
                    table_part, column_part = column_candidate
                elif len(column_candidate) == 1:
                    table_part, column_part = self._split_column_string(column_candidate[0])
                else:
                    continue
            else:
                table_part, column_part = self._split_column_string(column_candidate)

            column_norm = self._norm_ident(column_part)
            if not column_norm:
                continue

            table_norm = self._match_table(table_part, tables) if table_part else None
            if table_norm and column_norm in tables.get(table_norm, {}).get("col_norms", set()):
                linked_tables.add(table_norm)
                linked_columns.add((table_norm, column_norm))
            else:
                found = False
                for table_name, info in tables.items():
                    if column_norm in info.get("col_norms", set()):
                        linked_tables.add(table_name)
                        linked_columns.add((table_name, column_norm))
                        found = True
                if not found and table_norm:
                    linked_tables.add(table_norm)

        if not linked_tables and not linked_columns:
            linked_tables, linked_columns = self._lexical_link(question, tables)

        expanded_tables = set(linked_tables)
        for table_name, column_name in linked_columns:
            for fk in tables.get(table_name, {}).get("fks", []):
                if column_name in fk.get("cols", []) and fk.get("ref_table") in tables:
                    expanded_tables.add(fk["ref_table"])

        if len(expanded_tables) >= 2:
            expanded_tables.update(self._find_bridge_tables(tables, expanded_tables))

        return expanded_tables, linked_columns

    def _render_subset_schema(self, tables, linked_tables, linked_columns):
        if not linked_tables:
            return ""

        parts = []
        for table_name in sorted(linked_tables):
            info = tables.get(table_name)
            if not info:
                continue
            ddl = info.get("ddl", "").strip()
            if ddl:
                if not ddl.endswith(";"):
                    ddl += ";"
                parts.append(ddl)

        return "\n".join(parts)

    def _generate_sql(self, question, schema_text, linked_columns):
        schema_block = (schema_text or "").strip() or "No schema is available."
        linked_note = ""
        if linked_columns:
            cols = ", ".join(f"{t}.{c}" for t, c in sorted(linked_columns))
            linked_note = f"\nThe schema linker highlighted these likely relevant columns: {cols}."

        prompt = (
            "Use the following SQL schema to answer the question.\n\n"
            f"{schema_block}\n"
            f"{linked_note}\n\n"
            f"Question: {question}\n\n"
            "Return only one valid SQL query. No explanation."
        )
        system = "You are an expert text-to-SQL system. Output only SQL."
        text = self._llm_text(prompt, system=system, temperature=0.0, n=1)
        return self._extract_sql(text)

    def _repair_sql(self, question, sql, error, schema_text, linked_columns):
        schema_block = (schema_text or "").strip() or "No schema is available."
        linked_note = ""
        if linked_columns:
            cols = ", ".join(f"{t}.{c}" for t, c in sorted(linked_columns))
            linked_note = f"\nThe schema linker highlighted these likely relevant columns: {cols}."

        error_text = str(error or "").strip()
        if len(error_text) > 800:
            error_text = error_text[:800] + "..."

        prompt = (
            "The following SQL was generated for the question but failed.\n"
            "Correct it using the schema below.\n\n"
            f"Schema:\n{schema_block}\n"
            f"{linked_note}\n\n"
            f"Question: {question}\n\n"
            f"SQL:\n{sql}\n\n"
            f"Error:\n{error_text}\n\n"
            "Return only one corrected SQL query. No explanation."
        )
        system = "You are an expert SQL debugger. Output only SQL."
        text = self._llm_text(prompt, system=system, temperature=0.0, n=1)
        return self._extract_sql(text)

    def _execute_ok(self, sql):
        try:
            result = self.execute(sql)
        except Exception as exc:
            return False, str(exc)

        if result is None:
            return False, "execution returned no result"

        if isinstance(result, dict):
            return bool(result.get("ok")), str(result.get("error") or "")

        if isinstance(result, bool):
            return result, ""

        return True, ""

    def _extract_sql(self, text):
        if not text:
            return ""

        sql = ""
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""

        if sql:
            return self._clean_sql(str(sql))

        cleaned = str(text).strip()
        cleaned = re.sub(r"