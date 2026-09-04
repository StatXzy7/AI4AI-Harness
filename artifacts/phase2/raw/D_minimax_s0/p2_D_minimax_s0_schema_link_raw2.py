"""Prompt-twice schema-linked Text-to-SQL harness that first extracts relevant tables/columns, then generates SQL against the linked schema subset."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS0SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Schema linking - identify tables/columns relevant to the question
        link_prompt = (
            f"You are given a database schema and a natural language question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"List the exact table names and column names from the schema that are "
            f"needed to answer this question. Output ONLY a concise list of table "
            f"and column references, one per line, e.g.:\n"
            f"Table: students\n"
            f"Table: enrollments; Columns: student_id, course_id"
        )
        linked = self.llm(link_prompt, system="You extract relevant schema elements.", temperature=0.0, n=1)
        linked = (linked or "").strip()

        # Build a focused schema subset from the linked output; fall back to full schema
        # if nothing usable was returned.
        focused_schema = self._filter_schema(linked) if linked else self.schema

        # Step 2: Generate SQL against the linked/focused schema subset
        sql_prompt = (
            f"You are given a database schema (restricted to relevant tables/columns) "
            f"and a natural language question.\n\n"
            f"Relevant Schema:\n{focused_schema}\n\n"
            f"Linked schema references:\n{linked}\n\n"
            f"Question: {question}\n\n"
            f"Write a single SQL query that answers the question using only the "
            f"tables/columns listed above. Output only the SQL statement."
        )
        raw = self.llm(sql_prompt, system="You write precise SQLite-compatible SQL.", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw or "")

        # Repair pass if the SQL doesn't execute
        if sql and not self.execute(sql).get("ok", False):
            err = self.execute(sql).get("error", "")
            repair_prompt = (
                f"The following SQL failed to execute:\n