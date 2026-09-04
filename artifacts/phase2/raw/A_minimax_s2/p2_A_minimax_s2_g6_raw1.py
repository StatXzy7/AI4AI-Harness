"""Two-stage SQL generation: first stage produces an intermediate reasoning artifact, second stage consumes it to produce the final SQL."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G6(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        # Stage 1: produce an intermediate artifact -- a structured analysis that
        # identifies relevant tables/columns and the intended query shape.
        stage1_prompt = (
            "You are analyzing a Text-to-SQL problem.\n\n"
            f"SCHEMA:\n{schema}\n\n"
            f"QUESTION:\n{question}\n\n"
            "Produce an ANALYSIS with three sections:\n"
            "  TABLES: list the tables needed (comma-separated).\n"
            "  COLUMNS: list the exact column references needed, in the form table.column.\n"
            "  INTENT: one sentence describing what the query must return and any filters/aggregations.\n"
            "Do NOT write SQL. Only the analysis."
        )
        analysis = self.llm(stage1_prompt, system="You are a precise SQL analyst.", temperature=0.0, n=1).strip()

        # Stage 2: consume the analysis artifact and the original question to produce SQL.
        stage2_prompt = (
            "You are writing a SQL query. Use the ANALYSIS below as your plan.\n\n"
            f"SCHEMA:\n{schema}\n\n"
            f"QUESTION:\n{question}\n\n"
            f"ANALYSIS:\n{analysis}\n\n"
            "Write ONE SQL statement that answers the question. "
            "Output only the SQL, no prose."
        )
        raw = self.llm(stage2_prompt, system="You are an expert SQL generator.", temperature=0.0, n=1)

        sql = bridge.extract_sql(raw)
        if not sql:
            sql = raw.strip()
        return sql