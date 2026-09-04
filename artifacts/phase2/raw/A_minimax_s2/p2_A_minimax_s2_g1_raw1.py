"""Two-stage Text-to-SQL harness: first stage produces a focused schema sketch, second stage generates SQL conditioned on the sketch."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G1(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: ask the LLM to identify the minimal subset of the schema
        # that is relevant to the question, producing a compact "schema sketch".
        sketch_system = (
            "You are a database schema analyst. Given a full CREATE TABLE schema and a "
            "natural language question, output ONLY the minimal subset of tables and "
            "columns that are required to answer the question. Keep all CREATE TABLE "
            "definitions intact for the relevant tables, including PRIMARY KEY and "
            "FOREIGN KEY clauses. Do not include tables or columns that are not needed. "
            "Do not write any SQL. Do not write explanations."
        )
        sketch_prompt = (
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION:\n{question}\n\n"
            f"MINIMAL RELEVANT SCHEMA:"
        )
        sketch = self.llm(sketch_prompt, system=sketch_system, temperature=0.0, n=1)
        # Defensive: ensure we have a non-empty sketch, otherwise fall back to full schema.
        sketch = (sketch or "").strip()
        if "CREATE TABLE" not in sketch.upper():
            sketch = self.schema

        # Stage 2: generate the SQL conditioned on the focused schema sketch.
        sql_system = (
            "You are an expert SQLite SQL writer. Given a database schema and a natural "
            "language question, output exactly one SQL query that answers the question. "
            "Use only tables and columns present in the provided schema. Output ONLY the "
            "SQL statement, no prose, no markdown fences."
        )
        sql_prompt = (
            f"SCHEMA:\n{sketch}\n\n"
            f"QUESTION:\n{question}\n\n"
            f"SQL:"
        )
        raw = self.llm(sql_prompt, system=sql_system, temperature=0.0, n=1)
        final_sql = bridge.extract_sql(raw)
        if not final_sql:
            # Fallback: try to use the raw output directly if extraction failed.
            final_sql = (raw or "").strip()
        return final_sql