"""Two-View harness that generates SQL via two independent formulations, executes both, and returns the first non-empty result."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        join_sql_prompt = (
            "You are an expert SQL generator.\n"
            "Given the database schema and a natural language question, "
            "produce ONE valid SQL query that answers the question.\n"
            "Use JOINs where tables need to be combined.\n"
            "Return only the SQL, no explanations, no markdown fences.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )

        subquery_sql_prompt = (
            "You are an expert SQL generator.\n"
            "Given the database schema and a natural language question, "
            "produce ONE valid SQL query that answers the question.\n"
            "Use nested subqueries (WHERE IN / SELECT FROM) where applicable "
            "instead of JOINs when possible.\n"
            "Return only the SQL, no explanations, no markdown fences.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )

        system_msg = "You are a precise Text-to-SQL generator that emits only valid SQL."

        join_raw = self.llm(
            join_sql_prompt,
            system=system_msg,
            temperature=0.0,
            n=1,
        )
        sub_raw = self.llm(
            subquery_sql_prompt,
            system=system_msg,
            temperature=0.0,
            n=1,
        )

        join_sql = bridge.extract_sql(join_raw)
        sub_sql = bridge.extract_sql(subquery_sql_prompt) if False else bridge.extract_sql(sub_raw)

        join_sql = join_sql or ""
        sub_sql = sub_sql or ""

        join_result = None
        sub_result = None

        if join_sql.strip():
            join_result = self.execute(join_sql)

        if sub_sql.strip():
            sub_result = self.execute(sub_sql)

        join_ok = bool(join_result and join_result.get("ok"))
        sub_ok = bool(sub_result and sub_result.get("ok"))

        join_rows = (join_result.get("rows") if join_ok else []) or []
        sub_rows = (sub_result.get("rows") if sub_ok else []) or []

        if join_ok and len(join_rows) > 0:
            return join_sql
        if sub_ok and len(sub_rows) > 0:
            return sub_sql
        if join_ok:
            return join_sql
        if sub_ok:
            return sub_sql

        return join_sql or sub_sql or ""