"""Single greedy generation call with schema-grounded prompt construction, no iterative control-flow mechanism."""
# MECHANISM: plain
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G0(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema or ""

        system_prompt = (
            "You are an expert Text-to-SQL generator. "
            "Given a database schema and a natural language question, "
            "produce a single valid SQL query that answers the question. "
            "Use only tables and columns present in the schema. "
            "Prefer standard SQL compatible with SQLite. "
            "Output only the SQL query, with no prose, no Markdown fences, and no explanation."
        )

        user_prompt = (
            "Schema:\n"
            f"{schema}\n\n"
            "Question:\n"
            f"{question}\n\n"
            "SQL:"
        )

        raw = self.llm(
            user_prompt,
            system=system_prompt,
            temperature=0.0,
            n=1,
        )

        if isinstance(raw, list):
            raw = raw[0] if raw else ""

        sql = bridge.extract_sql(raw)
        return sql if sql else raw.strip()