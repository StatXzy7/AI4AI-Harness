"""Wraps a frozen weak solver by first prompting it to link schema items, then composing SQL against the linked subset."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS0SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Identify tables/columns referenced in the question via a dedicated linking pass.
        link_prompt = (
            "Given the database schema below and a natural language question, list the exact "
            "table names and column names from the schema that are needed to answer the question. "
            "Output only a concise bulleted list of referenced tables and columns, nothing else.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION:\n{question}\n\n"
            "REFERENCED TABLES AND COLUMNS:"
        )
        linked = self.llm(link_prompt, system="You are a precise schema linker.", temperature=0.0, n=1)

        # Step 2: Build a reduced schema view from the linked items (best-effort substring matching).
        linked_lower = linked.lower()
        keep_lines = []
        for line in self.schema.splitlines():
            ll = line.lower()
            # Keep structural lines (CREATE/INSERT/etc.) and any line that mentions a referenced token.
            if any(tok in ll for tok in linked_lower.replace(".", " ").replace(",", " ").split() if len(tok) > 2):
                keep_lines.append(line)
            elif ll.strip().startswith(("create", "insert", "table", "from", "join", "select", "where", "group", "order", "having")):
                keep_lines.append(line)
        reduced_schema = "\n".join(keep_lines) if keep_lines else self.schema

        # Step 3: Ask the weak solver to write SQL against the linked subset only.
        sql_prompt = (
            "You are a Text-to-SQL generator. Use ONLY the referenced tables and columns listed below "
            "(extracted from the full schema) to write a single SQL query that answers the question. "
            "Output only the SQL statement, no prose, no explanation.\n\n"
            f"LINKED SCHEMA ITEMS:\n{linked}\n\n"
            f"RELEVANT SCHEMA SNIPPET:\n{reduced_schema}\n\n"
            f"QUESTION:\n{question}\n\n"
            "SQL:"
        )
        raw = self.llm(sql_prompt, system="You write precise SQLite-compatible SQL.", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        # Step 4: Validate execution; on failure, retry once with a corrective hint against the linked subset.
        result = self.execute(sql)
        if not result.get("ok"):
            repair_prompt = (
                "The following SQL failed to execute. Rewrite it so it runs correctly, using only the "
                "linked schema items. Output only the corrected SQL.\n\n"
                f"LINKED SCHEMA ITEMS:\n{linked}\n\n"
                f"RELEVANT SCHEMA SNIPPET:\n{reduced_schema}\n\n"
                f"QUESTION:\n{question}\n\n"
                f"BAD SQL:\n{sql}\n\n"
                f"ERROR:\n{result.get('error', '')}\n\n"
                "CORRECTED SQL:"
            )
            raw2 = self.llm(repair_prompt, system="You debug and repair SQL.", temperature=0.0, n=1)
            sql = bridge.extract_sql(raw2)

        return sql