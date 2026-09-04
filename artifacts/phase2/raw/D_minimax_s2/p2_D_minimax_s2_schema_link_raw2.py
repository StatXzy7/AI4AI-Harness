"""Prompt-to-prompt schema-linking harness that asks the LLM to identify relevant tables and columns, then writes SQL against the linked schema subset."""
import re
from ..harness_base import SQLHarness
from .. import bridge


SCHEMA_LINK_SYSTEM = (
    "You are a schema linking module. Given a database schema and a natural language "
    "question, output ONLY the names of the tables and columns from the schema that are "
    "necessary to answer the question. List one table or column per line, prefixed with "
    "TABLE: or COLUMN: respectively. Do not output any explanation or SQL."
)

SQL_SYSTEM = (
    "You are a SQL expert. Given a database schema, a user question, and a list of "
    "already-linked relevant tables and columns, write a single SQLite-compatible SQL "
    "statement that answers the question. Output ONLY the SQL statement, no prose."
)


class P2P2DMinimaxS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # -------- Pass 1: Schema linking --------
        link_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"List the relevant tables and columns:"
        )
        link_response = self.llm(link_prompt, system=SCHEMA_SYSTEM if False else SCHEMA_LINK_SYSTEM,
                                 temperature=0.0, n=1)
        linked_subset = self._build_linked_subset(self.schema, link_response)

        # -------- Pass 2: SQL generation against the linked subset --------
        sql_prompt = (
            f"Full schema (for reference):\n{self.schema}\n\n"
            f"Relevant subset:\n{linked_subset}\n\n"
            f"Question: {question}\n\n"
            f"SQL:"
        )
        sql_response = self.llm(sql_prompt, system=SQL_SYSTEM, temperature=0.0, n=1)

        sql_candidate = bridge.extract_sql(sql_response)
        if not sql_candidate:
            sql_candidate = self._extract_sql_fallback(sql_response)

        # -------- Pass 3 (fallback): if execution fails, retry once with broader schema --------
        result = self.execute(sql_candidate)
        if not result.get("ok"):
            retry_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"The previous SQL failed with: {result.get('error', 'unknown error')}.\n"
                f"Write a corrected SQLite SQL statement. Output ONLY the SQL:"
            )
            retry_response = self.llm(retry_prompt, system=SQL_SYSTEM,
                                       temperature=0.0, n=1)
            retry_sql = bridge.extract_sql(retry_response)
            if not retry_sql:
                retry_sql = self._extract_sql_fallback(retry_response)
            if retry_sql:
                sql_candidate = retry_sql

        return sql_candidate

    # --------------------------------------------------------------------- #
    # Helpers
    # --------------------------------------------------------------------- #
    def _build_linked_subset(self, full_schema: str, link_response: str) -> str:
        """Parse the LLM's table/column list and return a trimmed schema fragment."""
        referenced_tables, referenced_columns = self._parse_link_response(link_response)
        if not referenced_tables and not referenced_columns:
            return full_schema

        lines = full_schema.splitlines()
        out_lines = []
        current_table = None
        keep_table = False

        for line in lines:
            stripped = line.strip()
            # Heuristic: CREATE TABLE statements (or similar table headers)
            table_match = re.match(
                r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\][]?(\w+)["`\]]?',
                stripped, re.IGNORECASE)
            if table_match:
                current_table = table_match.group(1)
                keep_table = (
                    not referenced_tables
                    or current_table.lower() in referenced_tables
                )
                if keep_table:
                    out_lines.append(line)
                continue

            if current_table is None:
                out_lines.append(line)
                continue

            if keep_table:
                # Keep lines that mention a referenced column, or all column lines
                # if no specific column filter was given.
                col_match = re.match(r'\s*["`[]?(\w+)["`]]?\s+', line)
                if col_match:
                    col_name = col_match.group(1).lower()
                    if not referenced_columns or col_name in referenced_columns:
                        out_lines.append(line)
                        continue
                # Always keep closing parens / comments for kept tables
                if line.strip().startswith(')') or line.strip().startswith('--'):
                    out_lines.append(line)

        return "\n".join(out_lines) if out_lines else full_schema

    @staticmethod
    def _parse_link_response(link_response: str):
        tables, columns = set(), set()
        for raw_line in link_response.splitlines():
            line = raw_line.strip().rstrip(',').rstrip(';').strip()
            if not line:
                continue
            upper = line.upper()
            if upper.startswith("TABLE:"):
                tables.add(line.split(":", 1)[1].strip().strip('`"[]').lower())
            elif upper.startswith("COLUMN:"):
                col_part = line.split(":", 1)[1].strip()
                # Allow "table.column" form -> grab column only
                if "." in col_part:
                    col_part = col_part.split(".")[-1]
                columns.add(col_part.strip('`"[]').lower())
            elif upper.startswith("TABLES:"):
                for t in line.split(":", 1)[1].split(","):
                    tables.add(t.strip().strip('`"[]').lower())
            elif upper.startswith("COLUMNS:"):
                for c in line.split(":", 1)[1].split(","):
                    c = c.strip().strip('`"[]')
                    if "." in c:
                        c = c.split(".")[-1]
                    columns.add(c)
        return tables, columns

    @staticmethod
    def _extract_sql_fallback(text: str) -> str:
        """Last-ditch SQL extractor: grab the first