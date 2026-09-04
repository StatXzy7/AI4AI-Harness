"""Schema-link the question to relevant tables/columns, then generate and repair SQL using only that subset."""
from ..harness_base import SQLHarness
from .. import bridge

import json
import re


class P2P2CQwenS0SchemaLink(SQLHarness):
    _CREATE_TABLE_RE = re.compile(
        r'CREATE\s+(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?'
        r'(?P<name>(?:[`"\[]?[A-Za-z_][\w$]*[`"\]]?)(?:\s*\.\s*[`"\[]?[A-Za-z_][\w$]*[`"\]]?)*)'
        r'\s*\(',
        re.IGNORECASE,
    )

    def solve(self, question: str) -> str:
        schema = (getattr(self, 'schema', '') or '').strip()

        links = self._schema_link(question, schema)
        known_tables = self._known_tables(schema)
        selected_tables = self._choose_tables(links.get('tables', []), known_tables, question)

        if selected_tables:
            linked_columns = self._normalize_columns(links.get('columns', {}), selected_tables)
            linked_schema = self._build_linked_schema(schema, selected_tables, linked_columns, question)
        else:
            linked_columns = {}
            linked_schema = schema

        if not linked_schema.strip():
            selected_tables = known_tables
            linked_schema = schema

        schema_text = self._annotate_schema(linked_schema, linked_columns)

        sql = self._generate_sql(question, schema_text, selected_tables)
        if not sql.strip():
            sql = self._generate_sql(question, schema, known_tables)

        for _ in range(3):
            sql = self._clean_sql(bridge.extract_sql(sql) or sql)
            if not sql:
                sql = self._generate_sql(question, schema_text, selected_tables)
                continue

            result = self._execute(sql)
            if result.get('ok'):
                return sql

            error = str(result.get('error') or 'unknown error')
            repair_schema = schema_text
            low = error.lower()
            if any(marker in low for marker in (
                'no such table',
                'unknown table',
                'table not found',
                'no such column',
                'unknown column',
                'column not found',
                'invalid column',
                'ambiguous column',
            )):
                repair_schema = schema

            sql = self._repair_sql(question, sql, error, repair_schema)

        return self._clean_sql(bridge.extract_sql(sql) or sql)

    def _schema_link(self, question, schema):
        if not schema.strip():
            return {'tables': [], 'columns': {}}

        system = 'You are a precise schema linker. Return only JSON.'
        prompt = (
            'Database schema:\n'
            f'{schema}\n\n'
            f'Question: {question}\n\n'
            'Identify the minimal tables and columns needed to answer the question. '
            'Include tables needed for joins and filters. '
            'Return exactly JSON of the form: '
            '{"tables": ["table_name"], "columns": {"table_name": ["column_name"]}}\n'
            'No markdown, no explanations.'
        )

        text = self._llm_text(prompt, system=system, temperature=0.0)
        data = self._parse_json(text)

        tables = []
        columns = {}

        if isinstance(data, dict):
            raw_tables = data.get('tables') or data.get('table_names') or data.get('Tables') or []
            if isinstance(raw_tables, str):
                raw_tables = [raw_tables]
            if isinstance(raw_tables, (list, tuple)):
                tables = [str(t) for t in raw_tables if str(t).strip()]

            raw_cols = data.get('columns') or data.get('cols') or data.get('Columns') or {}
            if isinstance(raw_cols, dict):
                for table, cols in raw_cols.items():
                    if isinstance(cols, str):
                        cols = [cols]
                    if isinstance(cols, (list, tuple)):
                        columns[str(table)] = [str(c) for c in cols if str(c).strip()]
            elif isinstance(raw_cols, (list, tuple)):
                for item in raw_cols:
                    s = str(item)
                    if '.' in s:
                        table, col = s.split('.', 1)
                        columns.setdefault(table, []).append(col)

        if not tables:
            known = self._known_tables(schema)
            low = text.lower()
            tables = [t for t in known if t in low]

        return {'tables': tables, 'columns': columns}

    def _parse_json(self, text):
        text = str(text or '').strip()
        if not text:
            return None

        try:
            return json.loads(text)
        except Exception:
            pass

        fence = re.search(r'