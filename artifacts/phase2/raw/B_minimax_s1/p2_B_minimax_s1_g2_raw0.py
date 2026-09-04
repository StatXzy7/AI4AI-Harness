"""Two-stage harness that first produces a focused schema sketch, then generates SQL conditioned on that sketch."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS1G2(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: ask the LLM to identify which tables/columns from the schema are relevant
        stage1_system = (
            "You are a schema-linking assistant. Given a database schema and a natural "
            "language question, output ONLY the minimal subset of tables and columns "
            "required to answer the question. List the relevant tables and their "
            "necessary columns. Do not write SQL."
        )
        stage1_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Relevant tables and columns:"
        )
        sketch = self.llm(stage1_prompt, system=stage1_system, temperature=0.0, n=1).strip()
        if not sketch:
            sketch = self.schema

        # Stage 2: generate SQL conditioned on the sketch
        stage2_system = (
            "You are a Text-to-SQL expert. Write a single SQLite-compatible SQL query "
            "that answers the question using the provided schema. Output only the SQL."
        )
        stage2_prompt = (
            f"Full schema (for reference):\n{self.schema}\n\n"
            f"Relevant schema subset (from linker):\n{sketch}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        raw = self.llm(stage2_prompt, system=stage2_system, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        # Light repair: if execution fails, do one targeted retry with the error fed back
        if sql:
            result = self.execute(sql)
            if not result.get("ok", False):
                repair_prompt = (
                    f"Schema:\n{self.schema}\n\n"
                    f"Relevant subset:\n{sketch}\n\n"
                    f"Question: {question}\n\n"
                    f"Your previous SQL:\n{sql}\n\n"
                    f"It failed with this error:\n{result.get('error', '').strip()}\n\n"
                    "Produce a corrected SQL query. Output only the SQL."
                )
                repaired = self.llm(repair_prompt, system=stage2_system, temperature=0.0, n=1)
                fixed = bridge.extract_sql(repaired)
                if fixed:
                    sql = fixed

        return sql if sql else raw.strip()