"""Two-stage SQL generation: schema-aware sketch first, then full SQL synthesis from the sketch."""
# MECHANISM: twostage

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS0G5(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: Produce a minimal "sketch" -- identifying which tables/columns/joins
        # are likely relevant, without writing full executable SQL. This constrains the
        # second stage so it doesn't have to simultaneously reason about schema choice
        # and SQL syntax.
        sketch_prompt = (
            "You are analyzing a natural language question against a database schema.\n\n"
            "SCHEMA:\n"
            f"{self.schema}\n\n"
            "QUESTION:\n"
            f"{question}\n\n"
            "Produce a short JSON sketch with these keys:\n"
            "  tables: list of relevant table names\n"
            "  columns: dict mapping table_name -> list of relevant column names\n"
            "  joins: list of join conditions (e.g. 'a.id = b.aid')\n"
            "  filters: list of WHERE-clause conditions expressed in English\n"
            "  aggregation: what (if anything) is being aggregated, in English\n"
            "  ordering: any ordering requirement, in English\n"
            "Output ONLY the JSON, nothing else."
        )
        sketch_raw = self.llm(sketch_prompt, system="You output only valid JSON.", temperature=0.0, n=1)

        # Stage 2: Produce the final SQL, conditioned on the sketch. The sketch acts
        # as a compressed intermediate artifact between NL and SQL.
        sql_prompt = (
            "You are a Text-to-SQL expert. Given a schema, a question, and an analysis "
            "sketch, write a single SQLite-compatible SQL query that answers the question.\n\n"
            "SCHEMA:\n"
            f"{self.schema}\n\n"
            "QUESTION:\n"
            f"{question}\n\n"
            "ANALYSIS SKETCH:\n"
            f"{sketch_raw}\n\n"
            "Write ONLY the SQL. Use SELECT ... FROM ... with appropriate JOINs and WHERE "
            "conditions. Do not include explanations or markdown fences."
        )
        sql_raw = self.llm(sql_prompt, system="You output only SQL.", temperature=0.0, n=1)

        sql = bridge.extract_sql(sql_raw)
        if not sql:
            sql = sketch_raw.strip()  # last-resort fallback

        return sql