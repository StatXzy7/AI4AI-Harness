"""Two-phase harness: first link relevant schema tables/columns, then generate SQL over that linked subset."""

from ..harness_base import SQLHarness
from .. import bridge
import json
import re


class P2P2CDeepseekS1SchemaLink(SQLHarness):
    """Two-phase schema linking then SQL generation over linked table/column subset."""

    def solve(self, question: str) -> str:
        full_schema = self.schema or ""

        # Phase 1: Identify relevant tables and columns.
        linking_prompt = (
            "You are given a database schema and a question.\n"
            "Identify ONLY the tables and columns needed to answer the question.\n"
            "Return a JSON object with two keys:\n"
            '  "tables": list of table names\n'
            '  "columns": list of column names, optionally qualified as "table.column"\n'
            "Do not include any explanation or markdown.\n\n"
            f"Schema:\n{full_schema}\n\n"
            f"Question:\n{question}\n"
        )
        raw_linking = self.llm(
            linking_prompt,
            system="You are a precise database schema linker.",
            temperature=0.0,
            n=1,
        )
        linking_text = self._response_text(raw_linking)
        linked = self._parse_json(linking_text)

        tables = self._as_list(linked.get("tables")) if isinstance(linked, dict) else []
        columns = self._as_list(linked.get("columns")) if isinstance(linked, dict) else []

        # Build linked subset schema.
        if tables:
            linked_schema = self._extract_table_ddl(full_schema, tables)
            if not linked_schema:
                linked_schema = full_schema
        else:
            linked_schema = full_schema

        # Build strict instructions for the SQL writer.
        if not tables and not columns:
            linked_note = (
                "No explicit linked set was produced; use the full schema below "
                "but select only the relevant tables and columns."
            )
        elif tables and not columns:
            linked_note = (
                f"Linked tables (use only these tables): {', '.join(tables)}.\n"
                "You may use any columns belonging to these linked tables."
            )
        elif columns and not tables:
            linked_note = (
                f"Linked columns (use only these columns): {', '.join(columns)}.\n"
                "Use the schema below to identify their tables."
            )
        else:
            linked_note = (
                f"Linked tables (use only these tables): {', '.join(tables)}.\n"
                f"Linked columns (use only these columns): {', '.join(columns)}.\n"
                "Do not reference any table or column outside these lists."
            )

        # Phase 2: Write SQL against the linked subset.
        sql_prompt = (
            "Using only the linked schema subset below, write a single SQLite SELECT query "
            "that answers the question.\n\n"
            f"{linked_note}\n\n"
            f"Linked schema:\n{linked_schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only the SQL query, with no markdown fences or explanation."
        )
        raw_sql = self.llm(
            sql_prompt,
            system="You are an expert SQL writer that strictly follows the linked schema.",
            temperature=0.0,
            n=1,
        )
        sql_text = self._response_text(raw_sql)
        return bridge.extract_sql(sql_text)

    @staticmethod
    def _response_text(response):
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            try:
                return response["choices"][0]["message"]["content"]
            except Exception:
                pass
            try:
                return response["message"]["content"]
            except Exception:
                pass
        if hasattr(response, "choices"):
            try:
                choice = response.choices[0]
                if hasattr(choice, "message"):
                    return choice.message.content
            except Exception:
                pass
        return str(response)

    @staticmethod
    def _parse_json(text):
        if not isinstance(text, str):
            return {}
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        start = text.find("{")
        if start == -1:
            return {}
        stack = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                stack += 1
            elif ch == "}":
                stack -= 1
                if stack == 0:
                    json_str = text[start : i + 1]
                    try:
                        data = json.loads(json_str)
                        if isinstance(data, dict):
                            return data
                    except Exception:
                        return {}
        return {}

    @staticmethod
    def _as_list(value):
        if isinstance(value, list):
            result = []
            for item in value:
                if isinstance(item, str):
                    cleaned = item.strip()
                    if cleaned:
                        result.append(cleaned)
            return result
        if isinstance(value, str):
            return [p.strip() for p in value.split(",") if p.strip()]
        return []

    @staticmethod
    def _extract_table_ddl(schema, tables):
        table_set = set()
        for t in tables:
            clean = t.strip().strip('`"[]')
            if "." in clean:
                clean = clean.split(".")[-1]
            if clean:
                table_set.add(clean.lower())

        if not table_set:
            return ""

        pattern = re.compile(
            r"(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[\w]+[`\"\]\w]*\s*\(.*?\)\s*;)",
            re.IGNORECASE | re.DOTALL,
        )
        matches = pattern.findall(schema)
        selected = []
        for ddl in matches:
            m = re.search(
                r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[\]]?([^`\"\[\]\(\s]+)[`\"\[\]]?",
                ddl,
                re.IGNORECASE,
            )
            if not m:
                continue
            name = m.group(1).strip().strip('`"[]')
            if name.lower() in table_set:
                selected.append(ddl.strip())

        if selected:
            return "\n\n".join(selected)

        # Fallback: if schema contains table names near "CREATE TABLE", try line chunks.
        lines = schema.splitlines()
        chunks = []
        current = []
        for line in lines:
            if re.match(r"\s*CREATE\s+TABLE", line, re.IGNORECASE):
                if current:
                    chunks.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            chunks.append("\n".join(current))

        selected_fallback = []
        for chunk in chunks:
            for t in tables:
                clean = t.strip().strip('`"[]')
                if "." in clean:
                    clean = clean.split(".")[-1]
                if re.search(r"\b" + re.escape(clean) + r"\b", chunk, re.IGNORECASE):
                    selected_fallback.append(chunk.strip())
                    break
        if selected_fallback:
            return "\n\n".join(selected_fallback)
        return ""