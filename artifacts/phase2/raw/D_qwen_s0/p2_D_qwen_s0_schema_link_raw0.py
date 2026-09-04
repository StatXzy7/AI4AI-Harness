"""First link the question to mentioned tables/columns, then generate SQL only against that linked schema subset."""
from ..harness_base import SQLHarness
from .. import bridge

import json
import re


class P2P2DQwenS0SchemaLink(SQLHarness):
    _LINK_SYSTEM = "You are a precise schema linker for Text-to-SQL. Output only valid JSON."
    _SQL_SYSTEM = "You are an expert SQL writer. Return only one SQL query."
    _REPAIR_SYSTEM = "You are an expert SQL debugger. Return only one corrected SQL query."

    _CONSTRAINT_FIRST_TOKENS = {
        "PRIMARY",
        "FOREIGN",
        "UNIQUE",
        "CHECK",
        "CONSTRAINT",
        "KEY",
        "INDEX",
        "FULL",
        "SPATIAL",
        "EXCLUDE",
    }

    _STOPWORDS = {
        "the", "and", "for", "with", "from", "select", "where", "join", "group",
        "order", "by", "sql", "table", "tables", "column", "columns", "what",
        "which", "list", "show", "give", "please", "count", "average", "sum",
        "min", "max", "each", "all", "any", "into", "have", "has", "that",
        "this", "their", "there", "when", "who", "whom", "whose", "are", "was",
        "were", "been", "being", "will", "would", "can", "could", "should",
        "may", "might", "some", "more", "most", "than", "then", "also", "only",
        "just", "over", "under", "between", "about", "after", "before",
        "during", "while", "because", "as", "at", "in", "on", "of", "to", "is",
        "it", "its", "a", "an", "or", "not", "no", "yes", "do", "does", "did",
        "done", "make", "makes", "made", "use", "using", "used",
    }

    _CREATE_HEAD_RE = re.compile(
        r"CREATE\s+(?:TEMPORARY\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"((?:\[[^\]]+\]|\"[^\"]+\"|`[^`]+`|[^\s(])+)\s*\(",
        re.IGNORECASE,
    )

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        schema = (getattr(self, "schema", "") or "").strip()

        if not question:
            return ""

        if not schema:
            sql = self._generate_sql(question, schema, linked=False)
            return self._extract_sql(sql) or sql

        link = self._link_schema(question, schema)

        if not link:
            sql = self._generate_sql(question, schema, linked=False)
            return self._finalize(question, schema, schema, sql)

        linked_schema = self._build_linked_schema(schema, link)
        sql = self._generate_sql(question, linked_schema, linked=True)
        return self._finalize(question, linked_schema, schema, sql)

    def _link_schema(self, question: str, schema: str):
        prompt = (
            "Identify the minimal schema subset needed to answer the question.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Return ONLY a JSON object with this shape:\n"
            "{\n"
            '  "tables": ["table_name"],\n'
            '  "columns": {\n'
            '    "table_name": ["column_name"]\n'
            "  }\n"
            "}\n"
            "Rules:\n"
            "- Include tables/columns needed for SELECT, JOIN, WHERE, GROUP BY, HAVING, ORDER BY.\n"
            "- Use exact names from the schema.\n"
            '- If a table is needed but columns are unclear, use ["*"] for that table.\n'
            "- Output no markdown and no explanation."
        )
        raw = self._llm_text(prompt, self._LINK_SYSTEM)
        link = self._parse_link(raw)
        if not link:
            link = self._heuristic_link(question, schema)
        return link

    def _parse_link(self, text: str):
        link = {}
        obj = self._parse_json(text)

        if isinstance(obj, dict):
            self._add_link_tables(link, obj.get("tables") or obj.get("table") or [])
            self._add_link_columns(link, obj.get("columns") or obj.get("fields") or {})
        elif isinstance(obj, list):
            self._add_link_columns_list(link, obj)

        return link

    def _parse_json(self, text: str):
        if not text:
            return None

        text = str(text).strip()
        text = re.sub(r"