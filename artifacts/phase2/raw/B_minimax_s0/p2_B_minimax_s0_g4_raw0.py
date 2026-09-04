"""Two-stage harness: first LLM drafts a query plan from the schema, second LLM drafts SQL conditioned on that plan, then executes and repairs on error."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS0G4(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: produce a textual query plan / skeleton referencing tables/columns
        plan_prompt = (
            "You are analyzing a database schema and a natural language question.\n"
            "Produce a concise query plan describing which tables and columns are needed, "
            "what joins are required, and what filters/aggregations apply. Do not write SQL.\n\n"
            "Schema:\n" + self.schema + "\n\n"
            "Question: " + question + "\n\n"
            "Query Plan:"
        )
        plan = self.llm(plan_prompt, system="You are a SQL query planner.", temperature=0.0, n=1).strip()

        # Stage 2: condition SQL generation on the plan produced above
        sql_prompt = (
            "You are writing a single SQL query for the given schema and question, "
            "guided by the provided query plan. Output exactly one SQL statement.\n\n"
            "Schema:\n" + self.schema + "\n\n"
            "Question: " + question + "\n\n"
            "Query Plan:\n" + plan + "\n\n"
            "SQL:"
        )
        raw_sql = self.llm(sql_prompt, system="You are a precise SQL generator.", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw_sql)

        # Lightweight repair loop: if execution fails, feed the error back
        for _ in range(2):
            result = self.execute(sql)
            if result.get("ok"):
                return sql
            err = result.get("error", "")
            repair_prompt = (
                "The following SQL failed to execute against the database. "
                "Fix the error and return exactly one corrected SQL statement.\n\n"
                "Schema:\n" + self.schema + "\n\n"
                "Question: " + question + "\n\n"
                "Query Plan:\n" + plan + "\n\n"
                "Failed SQL:\n" + sql + "\n\n"
                "Error:\n" + err + "\n\n"
                "Corrected SQL:"
            )
            raw_sql = self.llm(repair_prompt, system="You are a precise SQL fixer.", temperature=0.0, n=1)
            sql = bridge.extract_sql(raw_sql)

        return sql