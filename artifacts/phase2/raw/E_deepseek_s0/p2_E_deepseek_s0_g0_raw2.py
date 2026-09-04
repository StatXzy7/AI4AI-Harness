"""A Text-to-SQL harness that plans, generates, executes, and repairs SQL until it runs or attempts are exhausted."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G0(SQLHarness):
    def solve(self, question: str) -> str:
        def extract_sql(text: str) -> str:
            if not text:
                return ""
            return bridge.extract_sql(text) or text.strip()

        # Phase 1: build a lightweight query plan to guide SQL generation
        plan_prompt = (
            "You are a database query planner. Given the schema and question, "
            "list the relevant tables and columns, join conditions, filters, "
            "grouping/aggregations, and sorting. Be concise.\n\n"
            f"Schema:\n{self.schema}\n\nQuestion:\n{question}"
        )
        plan = self.llm(plan_prompt, system="You are a SQL planning assistant.", temperature=0.0, n=1) or ""

        # Phase 2: generate initial SQL from the plan
        gen_prompt = (
            "Write a single SQLite query that answers the question.\n"
            "Use the query plan to guide your SQL.\n"
            "Output only the SQL query.\n\n"
            f"Schema:\n{self.schema}\n\nQuestion:\n{question}\n\nPlan:\n{plan}"
        )
        generated = self.llm(gen_prompt, system="You are an expert Text-to-SQL assistant.", temperature=0.0, n=1)
        sql = extract_sql(generated)

        if not sql:
            return ""

        # Phase 3: execute and repair using runtime feedback
        max_repair_attempts = 3

        for _ in range(max_repair_attempts):
            result = self.execute(sql)
            if isinstance(result, dict) and result.get("ok"):
                return sql

            error = result.get("error", "Unknown execution error") if isinstance(result, dict) else str(result)

            repair_prompt = (
                "The following SQLite query failed. Produce a corrected SQLite query.\n"
                "Output only the SQL query.\n\n"
                f"Schema:\n{self.schema}\n\nQuestion:\n{question}\n\n"
                f"Previous SQL:\n{sql}\n\nError:\n{error}"
            )
            repaired = self.llm(repair_prompt, system="You are a SQL repair assistant.", temperature=0.0, n=1)
            repaired_sql = extract_sql(repaired)

            if repaired_sql and repaired_sql != sql:
                sql = repaired_sql
                continue

            # If the model did not change the SQL, ask for a full rewrite once.
            rewrite_prompt = (
                "Rewrite the SQL query from scratch to avoid the error.\n"
                "Output only the SQL query.\n\n"
                f"Schema:\n{self.schema}\n\nQuestion:\n{question}\n\nError:\n{error}"
            )
            rewritten = self.llm(rewrite_prompt, system="You are a SQL repair assistant.", temperature=0.0, n=1)
            rewritten_sql = extract_sql(rewritten)

            if rewritten_sql and rewritten_sql != sql:
                sql = rewritten_sql

        return sql