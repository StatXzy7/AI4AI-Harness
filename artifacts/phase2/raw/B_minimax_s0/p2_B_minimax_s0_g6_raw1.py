"""Two-stage harness that extracts referenced schema elements, then generates SQL with column hints."""
# MECHANISM: twostage    -- an earlier LLM stage produces an artifact a later stage consumes

import json
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS0G6(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: extract likely relevant tables/columns from the schema using the question.
        # We ask the LLM to pick a minimal subset of schema elements that the question needs.
        extract_prompt = (
            "Given the database schema below and a natural language question, list the exact "
            "table names and column names from the schema that are required to answer the "
            "question. Output ONLY a JSON object with keys 'tables' and 'columns', each a list "
            "of strings. Use the exact identifiers as they appear in the schema. Do not include "
            "any other text.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION:\n{question}\n\n"
            "JSON:"
        )
        extract_text = self.llm(extract_prompt, system="", temperature=0.0, n=1)
        hint = self._parse_hints(extract_text)

        # Stage 2: generate SQL conditioned on the question, the schema, and the extracted hints.
        # The hints act as a soft "skeleton" that constrains the generation to relevant elements.
        hint_block = ""
        if hint["tables"] or hint["columns"]:
            hint_block = (
                "\n\nRELEVANT SCHEMA ELEMENTS (extracted from the question; use these as the "
                "primary reference, but you may reference other schema elements if strictly "
                "necessary):\n"
                f"Tables: {', '.join(hint['tables']) if hint['tables'] else '(none identified)'}\n"
                f"Columns: {', '.join(hint['columns']) if hint['columns'] else '(none identified)'}"
            )

        gen_prompt = (
            f"You are a SQL expert. Given the schema and question below, write a single SQLite "
            f"SQL query that answers the question. Output ONLY the SQL statement, with no "
            f"explanation, no markdown fences, and no commentary.\n\n"
            f"SCHEMA:\n{self.schema}\n"
            f"{hint_block}\n\n"
            f"QUESTION:\n{question}\n\n"
            f"SQL:"
        )
        raw = self.llm(gen_prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        # Sanity check: if execution fails and we got no useful hints, retry once with
        # explicit column-name guidance extracted from the raw output of stage 1.
        if sql:
            result = self.execute(sql)
            if not result["ok"]:
                # Fallback: regenerate, this time listing candidate column names inline so the
                # model is forced to ground its query in real schema identifiers.
                retry_prompt = (
                    "The previous SQL attempt failed with an execution error. Rewrite the query. "
                    "Use ONLY table and column names that literally appear in the schema. "
                    "Output ONLY the corrected SQL.\n\n"
                    f"SCHEMA:\n{self.schema}\n"
                    f"{hint_block}\n\n"
                    f"QUESTION:\n{question}\n\n"
                    f"PREVIOUS ERROR:\n{result['error']}\n\n"
                    f"CORRECTED SQL:"
                )
                retry_text = self.llm(retry_prompt, system="", temperature=0.0, n=1)
                sql2 = bridge.extract_sql(retry_text)
                if sql2:
                    sql = sql2

        return sql if sql else ""

    def _parse_hints(self, text: str) -> dict:
        """Best-effort parse of the stage-1 JSON output. Falls back to schema-token scan."""
        default = {"tables": [], "columns": []}
        if not text:
            return default

        # Try strict JSON parse first.
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        candidate = m.group(0) if m else text
        try:
            obj = json.loads(candidate)
            tables = [str(t) for t in obj.get("tables", []) if isinstance(t, (str, int))]
            cols = [str(c) for c in obj.get("columns", []) if isinstance(c, (str, int))]
            return {"tables": tables, "columns": cols}
        except Exception:
            pass

        # Fallback: scan the text for tokens that look like identifiers and intersect with schema.
        schema_tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", self.schema or ""))
        # Filter to tokens that are likely schema elements (longer than 2 chars, not pure keywords).
        kw = {
            "select", "from", "where", "join", "inner", "left", "right", "outer", "on",
            "group", "by", "order", "having", "limit", "offset", "as", "and", "or", "not",
            "null", "is", "in", "between", "like", "case", "when", "then", "else", "end",
            "distinct", "count", "sum", "avg", "min", "max", "int", "integer", "text",
            "varchar", "char", "date", "datetime", "real", "float", "boolean",
        }
        candidates = [
            t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text)
            if t.lower() not in kw and len(t) > 2 and t in schema_tokens
        ]
        # Heuristic: tokens that are NOT in any other token (i.e., tables) vs substrings (columns).
        tables, columns = [], []
        for c in candidates:
            others = [x for x in candidates if x != c]
            if not any(c in o for o in others):
                tables.append(c)
            else:
                columns.append(c)
        # Deduplicate while preserving order.
        seen = set()
        tables = [t for t in tables if not (t in seen or seen.add(t))]
        seen2 = set()
        columns = [c for c in columns if not (c in seen2 or seen2.add(c))]
        return {"tables": tables[:10], "columns": columns[:20]}